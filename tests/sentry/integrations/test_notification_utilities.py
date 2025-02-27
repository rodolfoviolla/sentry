from __future__ import annotations

from typing import Mapping

from sentry.integrations.notifications import get_integrations_by_channel_by_recipient
from sentry.models import Integration, User
from sentry.services.hybrid_cloud.actor import RpcActor
from sentry.services.hybrid_cloud.integration import RpcIntegration, integration_service
from sentry.testutils.cases import TestCase
from sentry.testutils.helpers.notifications import DummyNotification
from sentry.types.integrations import ExternalProviders


class TestNotificationUtilities(TestCase):
    def setUp(self):
        super().setUp()
        self.notification = DummyNotification(self.organization)

        self.external_user_id_1 = "UXXXXXXX1"
        self.integration = self.create_slack_integration(self.notification.organization)
        self.api_integration = integration_service._serialize_integration(self.integration)

        self.user_2 = self.create_user()
        self.external_team_id_2 = "TXXXXXXX2"
        self.integration2 = self.create_slack_integration(
            self.notification.organization,
            external_id=self.external_team_id_2,
            user=self.user_2,
            identity_external_id=self.external_team_id_2,
        )
        self.api_integration2 = integration_service._serialize_integration(self.integration2)

    def _assert_integrations_are(
        self,
        actual: Mapping[RpcActor, Mapping[str, RpcIntegration | Integration]],
        expected: Mapping[User, Mapping[str, RpcIntegration | Integration]],
    ):
        assert actual == {RpcActor.from_rpc_user(k): v for (k, v) in expected.items()}

    def test_simple(self):
        integrations_by_channel_by_recipient = get_integrations_by_channel_by_recipient(
            self.notification.organization,
            [self.user],
            ExternalProviders.SLACK,
        )

        self._assert_integrations_are(
            integrations_by_channel_by_recipient,
            {self.user: {self.external_user_id_1: self.api_integration}},
        )

    def test_matching_idp_and_identity_external_id(self):
        """
        Test that rows where identity.external_id is equal to idp.external_id are excluded.
        """
        integrations_by_channel_by_recipient = get_integrations_by_channel_by_recipient(
            self.notification.organization,
            [self.user_2],
            ExternalProviders.SLACK,
        )

        self._assert_integrations_are(integrations_by_channel_by_recipient, {self.user_2: {}})

    def test_multiple(self):
        integrations_by_channel_by_recipient = get_integrations_by_channel_by_recipient(
            self.notification.organization,
            [self.user, self.user_2],
            ExternalProviders.SLACK,
        )

        self._assert_integrations_are(
            integrations_by_channel_by_recipient,
            {
                self.user: {self.external_user_id_1: self.api_integration},
                self.user_2: {},
            },
        )
