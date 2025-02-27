from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from sentry import audit_log, features
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.organization import OrganizationEndpoint, OrganizationPermission
from sentry.api.exceptions import ConflictError, ResourceDoesNotExist
from sentry.api.paginator import OffsetPaginator
from sentry.api.serializers import serialize
from sentry.api.serializers.models.team import TeamSerializer
from sentry.models import (
    ExternalActor,
    OrganizationMember,
    OrganizationMemberTeam,
    Team,
    TeamStatus,
)
from sentry.search.utils import tokenize_query
from sentry.signals import team_created
from sentry.utils.snowflake import MaxSnowflakeRetryError

CONFLICTING_SLUG_ERROR = "A team with this slug already exists."


# OrganizationPermission + team:write
class OrganizationTeamsPermission(OrganizationPermission):
    scope_map = {
        "GET": ["org:read", "org:write"],
        "POST": ["org:write", "team:write"],
    }


class TeamPostSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)
    slug = serializers.RegexField(
        r"^[a-z0-9_\-]+$",
        max_length=50,
        required=False,
        allow_null=True,
        error_messages={
            "invalid": _(
                "Enter a valid slug consisting of lowercase letters, "
                "numbers, underscores or hyphens."
            )
        },
    )
    idp_provisioned = serializers.BooleanField(required=False, default=False)
    set_team_admin = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not (attrs.get("name") or attrs.get("slug")):
            raise ValidationError("Name or slug is required")
        return attrs


@region_silo_endpoint
class OrganizationTeamsEndpoint(OrganizationEndpoint):
    permission_classes = (OrganizationTeamsPermission,)

    def team_serializer_for_post(self):
        # allow child routes to supply own serializer, used in SCIM teams route
        return TeamSerializer()

    def get(self, request: Request, organization) -> Response:
        """
        List an Organization's Teams
        ````````````````````````````

        Return a list of teams bound to a organization.

        :pparam string organization_slug: the slug of the organization for
                                          which the teams should be listed.
        :param string detailed: Specify "0" to return team details that do not include projects
        :auth: required
        """
        # TODO(dcramer): this should be system-wide default for organization
        # based endpoints
        if request.auth and hasattr(request.auth, "project"):
            return Response(status=403)

        queryset = (
            Team.objects.filter(organization=organization, status=TeamStatus.ACTIVE)
            .order_by("slug")
            .select_related("organization")  # Used in TeamSerializer
        )

        query = request.GET.get("query")

        if query:
            tokens = tokenize_query(query)
            for key, value in tokens.items():
                if key == "hasExternalTeams":
                    has_external_teams = "true" in value
                    if has_external_teams:
                        queryset = queryset.filter(
                            actor_id__in=ExternalActor.objects.filter(
                                organization=organization
                            ).values_list("actor_id")
                        )
                    else:
                        queryset = queryset.exclude(
                            actor_id__in=ExternalActor.objects.filter(
                                organization=organization
                            ).values_list("actor_id")
                        )

                elif key == "query":
                    value = " ".join(value)
                    queryset = queryset.filter(Q(name__icontains=value) | Q(slug__icontains=value))
                elif key == "slug":
                    queryset = queryset.filter(slug__in=value)
                elif key == "id":
                    queryset = queryset.filter(id__in=value)
                else:
                    queryset = queryset.none()

        is_detailed = request.GET.get("detailed", "1") != "0"

        expand = ["projects", "externalTeams"] if is_detailed else []

        return self.paginate(
            request=request,
            queryset=queryset,
            order_by="slug",
            on_results=lambda x: serialize(x, request.user, TeamSerializer(expand=expand)),
            paginator_cls=OffsetPaginator,
        )

    def should_add_creator_to_team(self, request: Request):
        return request.user.is_authenticated

    def post(self, request: Request, organization, **kwargs) -> Response:
        """
        Create a new Team
        ``````````````````

        Create a new team bound to an organization.  Only the name of the
        team is needed to create it, the slug can be auto generated.

        :pparam string organization_slug: the slug of the organization the
                                          team should be created for.
        :qparam string name: the optional name of the team.
        :qparam string slug: the optional slug for this team. If not provided it will be auto
                             generated from the name.
        :qparam bool set_team_admin: If this is true, the user is added to the as a Team Admin
                                instead of regular member
        :auth: required
        """
        serializer = TeamPostSerializer(data=request.data)

        if not serializer.is_valid():
            raise ValidationError(serializer.errors)

        result = serializer.validated_data
        set_team_admin = result.get("set_team_admin")

        if set_team_admin:
            if not features.has("organizations:team-roles", organization) or not features.has(
                "organizations:team-project-creation-all", organization
            ):
                raise ResourceDoesNotExist(
                    detail="You do not have permission to join a new team as a team admin"
                )
            if not self.should_add_creator_to_team(request):
                raise ValidationError(
                    {"detail": "You do not have permission to join a new team as a Team Admin"},
                )
        try:
            # Wrap team creation and member addition in same transaction
            with transaction.atomic():
                team = Team.objects.create(
                    name=result.get("name") or result["slug"],
                    slug=result.get("slug"),
                    idp_provisioned=result.get("idp_provisioned", False),
                    organization=organization,
                )
                team_created.send_robust(
                    organization=organization,
                    user=request.user,
                    team=team,
                    sender=self.__class__,
                )
                if self.should_add_creator_to_team(request):
                    member = OrganizationMember.objects.get(
                        user=request.user, organization=organization
                    )
                    OrganizationMemberTeam.objects.create(
                        team=team,
                        organizationmember=member,
                        role="admin" if set_team_admin else None,
                    )
        except (IntegrityError, MaxSnowflakeRetryError):
            raise ConflictError(
                {
                    "non_field_errors": [CONFLICTING_SLUG_ERROR],
                    "detail": CONFLICTING_SLUG_ERROR,
                }
            )
        except OrganizationMember.DoesNotExist:
            # team is automatically rolledback if exception raised in atomic block
            if set_team_admin:
                raise PermissionDenied(
                    detail="You must be a member of the organization to join a new team as a Team Admin"
                )
        else:
            self.create_audit_entry(
                request=request,
                organization=organization,
                target_object=team.id,
                event=audit_log.get_event_id("TEAM_ADD"),
                data=team.get_audit_log_data(),
            )
            return Response(
                serialize(team, request.user, self.team_serializer_for_post()),
                status=201,
            )
