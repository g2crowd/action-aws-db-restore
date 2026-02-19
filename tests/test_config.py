import os

import pytest
from src.config import *

ASSUME_ROLE_DISABLED = None


class TestConfig:
    def test_does_config_exist_when_file_present(self):
        assert does_config_exist(schema_dir() + "config.json") is True

    def test_does_config_exist_when_file_not_present(self):
        assert does_config_exist(schema_dir() + "conf.json") is False

    def test_load_config_exists_when_file_present(self):
        assert load_config(schema_dir() + "config.json") is not None

    def test_load_config_exists_when_file_not_present(self):
        assert load_config(schema_dir() + "conf.json") is None

    @pytest.fixture
    def data(self):
        return {
            "ClusterMode": False,
            "DeleteExistingTarget": True,
            "Source": {
                "Share": {
                    "AssumeRole": "arn:aws:iam::3211251512:role/db_restore_share_role",
                    "TargetAccount": "11223334544",
                    "SourceKmsKey": "alias/db_restore",
                    "TargetKmsKey": "alias/aws/rds",
                },
                "DBIdentifier": "dash-staging",
            },
            "Target": {
                "AssumeRole": "arn:aws:iam::11223334544:role/db_restore_role",
                "DBIdentifier": "dash-staging",
                "VpcSecurityGroupIds": "sg-076cd3b3c6",
                "DBSubnetGroupName": "${env:PRIVATE_SUBNET}",
                "CopyTagsToSnapshot": True,
                "DBInstanceClass": "db.t4g.large",
                "PubliclyAccessible": False,
                "Tags": [{"Key": "owner", "Value": "snapshot_restore"}],
            },
        }

    def test_is_valid(self, data):
        status, _ = is_valid(data)
        assert status is True

    def test_is_valid_missing_required_property_cluster_mode(self, data):
        invalid_data = data.copy()
        del invalid_data["Target"]["Tags"]
        status, _ = is_valid(invalid_data)
        assert status is False

    def test_is_valid_missing_required_property_tags(self, data):
        invalid_data = data.copy().pop("ClusterMode")
        status, _ = is_valid(invalid_data)
        assert status is False

    def test_is_valid_missing_optional_property_share(self, data):
        valid_data = data.copy()
        del valid_data["Source"]["Share"]
        status, _ = is_valid(valid_data)
        assert status is True

    def test_is_sharing_enabled_with_sharing_property(self, data):
        assert is_sharing_enabled(data["Source"]) is not None

    def test_is_sharing_enabled_without_sharing_property(self, data):
        valid_data = data.copy()
        del valid_data["Source"]["Share"]
        assert is_sharing_enabled(valid_data) is False

    def test_replace_placeholder_env_not_present(self, data):
        parsed_data = replace_placeholder(data, ASSUME_ROLE_DISABLED)
        assert parsed_data["Target"]["DBSubnetGroupName"] is None

    def test_replace_placeholder_env_present(self, data):
        key = "PRIVATE_SUBNET"
        value = "staging-global-private"
        os.environ[key] = value
        parsed_data = replace_placeholder(data, ASSUME_ROLE_DISABLED)
        assert parsed_data["Target"]["DBSubnetGroupName"] == value
