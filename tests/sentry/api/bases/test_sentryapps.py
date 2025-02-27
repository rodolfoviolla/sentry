import unittest
from unittest.mock import patch

import pytest
from django.http import Http404

from sentry.api.bases.sentryapps import (
    SentryAppBaseEndpoint,
    SentryAppInstallationBaseEndpoint,
    SentryAppInstallationPermission,
    SentryAppPermission,
    add_integration_platform_metric_tag,
)
from sentry.testutils import TestCase
from sentry.testutils.helpers.faux import Mock
from sentry.testutils.silo import control_silo_test


class SentryAppPermissionTest(TestCase):
    def setUp(self):
        self.permission = SentryAppPermission()
        self.user = self.create_user()
        self.org = self.create_organization(owner=self.user)

        self.sentry_app = self.create_sentry_app(name="foo", organization=self.org)

        self.request = self.make_request(user=self.user, method="GET")

    def test_request_user_is_app_owner_succeeds(self):
        assert self.permission.has_object_permission(self.request, None, self.sentry_app)

    def test_request_user_is_not_app_owner_fails(self):
        self.request.user = self.create_user()

        with pytest.raises(Http404):
            self.permission.has_object_permission(self.request, None, self.sentry_app)

    def test_has_permission(self):
        from sentry.models import ApiToken

        token = ApiToken.objects.create(user=self.user, scope_list=["event:read", "org:read"])
        self.request = self.make_request(user=None, auth=token, method="GET")
        assert self.permission.has_permission(self.request, None)


@control_silo_test(stable=True)
class SentryAppBaseEndpointTest(TestCase):
    def setUp(self):
        self.endpoint = SentryAppBaseEndpoint()

        self.user = self.create_user()
        self.org = self.create_organization(owner=self.user)

        self.request = self.make_request(user=self.user, method="GET")

        self.sentry_app = self.create_sentry_app(name="foo", organization=self.org)

    def test_retrieves_sentry_app(self):
        args, kwargs = self.endpoint.convert_args(self.request, self.sentry_app.slug)
        assert kwargs["sentry_app"].id == self.sentry_app.id

    def test_raises_when_sentry_app_not_found(self):
        with pytest.raises(Http404):
            self.endpoint.convert_args(self.request, "notanapp")


@control_silo_test(stable=True)
class SentryAppInstallationPermissionTest(TestCase):
    def setUp(self):
        self.permission = SentryAppInstallationPermission()

        self.user = self.create_user()
        self.member = self.create_user()
        self.org = self.create_organization(owner=self.member)

        self.sentry_app = self.create_sentry_app(name="foo", organization=self.org)

        self.installation = self.create_sentry_app_installation(
            slug=self.sentry_app.slug, organization=self.org, user=self.user
        )

        self.request = self.make_request(user=self.user, method="GET")

    def test_missing_request_user(self):
        self.request.user = None

        assert not self.permission.has_object_permission(self.request, None, self.installation)

    def test_request_user_in_organization(self):
        self.request = self.make_request(user=self.member, method="GET")

        assert self.permission.has_object_permission(self.request, None, self.installation)

    def test_request_user_not_in_organization(self):
        with pytest.raises(Http404):
            self.permission.has_object_permission(self.request, None, self.installation)


@control_silo_test(stable=True)
class SentryAppInstallationBaseEndpointTest(TestCase):
    def setUp(self):
        self.endpoint = SentryAppInstallationBaseEndpoint()

        self.user = self.create_user()
        self.org = self.create_organization(owner=self.user)

        self.request = self.make_request(user=self.user, method="GET")

        self.sentry_app = self.create_sentry_app(name="foo", organization=self.org)

        self.installation = self.create_sentry_app_installation(
            slug=self.sentry_app.slug, organization=self.org, user=self.user
        )

    def test_retrieves_installation(self):
        args, kwargs = self.endpoint.convert_args(self.request, self.installation.uuid)
        assert kwargs["installation"].id == self.installation.id

    def test_raises_when_sentry_app_not_found(self):
        with pytest.raises(Http404):
            self.endpoint.convert_args(self.request, "1234")


@control_silo_test(stable=True)
class AddIntegrationPlatformMetricTagTest(unittest.TestCase):
    @patch("sentry.api.bases.sentryapps.add_request_metric_tags")
    def test_record_platform_integration_metric(self, add_request_metric_tags):
        @add_integration_platform_metric_tag
        def get(self, request, *args, **kwargs):
            pass

        request = Mock()
        endpoint = Mock(request=request)

        get(endpoint, request)

        add_request_metric_tags.assert_called_with(request, integration_platform=True)
