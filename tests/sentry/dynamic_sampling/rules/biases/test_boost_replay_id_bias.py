import pytest

from sentry.dynamic_sampling.rules.biases.boost_replay_id_bias import BoostReplayIdBias


@pytest.mark.skip("The replay bias is temporarily disabled.")
@pytest.mark.django_db
def test_generate_bias_rules_v2(default_project):
    rules = BoostReplayIdBias().generate_rules(project=default_project, base_sample_rate=0.1)
    assert rules == [
        {
            "condition": {
                "inner": {
                    "name": "trace.replay_id",
                    "op": "eq",
                    "value": None,
                    "options": {"ignoreCase": True},
                },
                "op": "not",
            },
            "id": 1005,
            "samplingValue": {"type": "sampleRate", "value": 1.0},
            "type": "trace",
        },
    ]
