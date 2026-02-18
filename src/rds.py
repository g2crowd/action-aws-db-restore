import logging
from datetime import datetime
from operator import itemgetter

import boto3
from botocore.exceptions import ClientError

LOGGER = logging.getLogger("root")


def init_client(assumed_role):
    if assumed_role is None:
        client = boto3.client("rds")
    else:
        client = boto3.client(
            "rds",
            aws_access_key_id=assumed_role["AccessKeyId"],
            aws_secret_access_key=assumed_role["SecretAccessKey"],
            aws_session_token=assumed_role["SessionToken"],
        )
    return client


def get_waiter_config():
    return {"Delay": 60, "MaxAttempts": 300}


def does_target_exists(client, db_identifier, cluster_mode):
    if cluster_mode:
        response = client.describe_db_clusters(
            Filters=[{"Name": "db-cluster-id", "Values": [db_identifier]}]
        )
        if len(response["DBClusters"]) == 0:
            return False

    else:
        response = client.describe_db_instances(
            Filters=[{"Name": "db-instance-id", "Values": [db_identifier]}]
        )
        if len(response["DBInstances"]) == 0:
            return False
    return True


def get_latest_snapshot(client, db_identifier, cluster_mode):
    if cluster_mode:
        response = client.describe_db_cluster_snapshots(
            DBClusterIdentifier=db_identifier
        )
        if not response["DBClusterSnapshots"]:
            return None
        sorted_keys = sorted(
            response["DBClusterSnapshots"],
            key=itemgetter("SnapshotCreateTime"),
            reverse=True,
        )
        snapshot_arn = sorted_keys[0]["DBClusterSnapshotArn"]
    else:
        response = client.describe_db_snapshots(
            DBInstanceIdentifier=db_identifier, SnapshotType="automated"
        )
        if not response["DBSnapshots"]:
            return None
        sorted_keys = sorted(
            response["DBSnapshots"], key=itemgetter("SnapshotCreateTime"), reverse=True
        )
        snapshot_arn = sorted_keys[0]["DBSnapshotArn"]
    return snapshot_arn


def delete_rds(client, db_identifier, cluster_mode):
    LOGGER.info("Deleting %s db" % db_identifier)
    try:
        if cluster_mode:
            LOGGER.info("Deleting db instance")
            response = client.describe_db_clusters(
                DBClusterIdentifier=db_identifier
            )
            db_instance_identifier = response["DBClusters"][0]["DBClusterMembers"][0]["DBInstanceIdentifier"]
            client.delete_db_instance(
                DBInstanceIdentifier=db_instance_identifier,
                SkipFinalSnapshot=True,
                DeleteAutomatedBackups=True,
            )
            waiter = client.get_waiter("db_instance_deleted")
            waiter.wait(
                DBInstanceIdentifier=db_instance_identifier, WaiterConfig=get_waiter_config()
            )
            LOGGER.info("Deleting %s db cluster" % db_identifier)
            client.delete_db_cluster(
                DBClusterIdentifier=db_identifier, SkipFinalSnapshot=True
            )
            waiter = client.get_waiter("db_cluster_deleted")
            waiter.wait(
                DBClusterIdentifier=db_identifier, WaiterConfig=get_waiter_config()
            )
        else:
            client.delete_db_instance(
                DBInstanceIdentifier=db_identifier,
                SkipFinalSnapshot=True,
                DeleteAutomatedBackups=True,
            )
            waiter = client.get_waiter("db_instance_deleted")
            waiter.wait(
                DBInstanceIdentifier=db_identifier, WaiterConfig=get_waiter_config()
            )
    except ClientError as err:
        LOGGER.error(
            "{}: {}".format(
                err.response["Error"]["Code"], err.response["Error"]["Message"]
            )
        )
        return False
    return True


def update_identifier(client, source, target, cluster_mode):
    LOGGER.info("Modifying DB identifier {} to {}".format(source, target))
    try:
        if cluster_mode:
            client.modify_db_cluster(
                DBClusterIdentifier=source,
                NewDBClusterIdentifier=target,
                ApplyImmediately=True,
            )
        else:
            client.modify_db_instance(
                DBInstanceIdentifier=source,
                NewDBInstanceIdentifier=target,
                ApplyImmediately=True,
            )
    except ClientError as err:
        LOGGER.error(
            "{}: {}".format(
                err.response["Error"]["Code"], err.response["Error"]["Message"]
            )
        )
        return False
    return True


def copy_snapshot(client, source, target, kms_key, cluster_mode):
    try:
        if cluster_mode:
            response = client.copy_db_cluster_snapshot(
                SourceDBClusterSnapshotIdentifier=source,
                TargetDBClusterSnapshotIdentifier=target,
                KmsKeyId=kms_key,
            )
            target_snapshot = response["DBClusterSnapshot"][
                "DBClusterSnapshotIdentifier"
            ]
            target_snapshot_arn = response["DBClusterSnapshot"]["DBClusterSnapshotArn"]
            target_engine = response["DBClusterSnapshot"]["Engine"]
            target_engine_version = response["DBClusterSnapshot"]["EngineVersion"]
            waiter = client.get_waiter("db_cluster_snapshot_available")
            waiter.wait(
                DBClusterSnapshotIdentifier=target_snapshot_arn,
                WaiterConfig=get_waiter_config(),
            )

        else:
            response = client.copy_db_snapshot(
                SourceDBSnapshotIdentifier=source,
                TargetDBSnapshotIdentifier=target,
                KmsKeyId=kms_key,
            )
            target_snapshot = response["DBSnapshot"]["DBSnapshotIdentifier"]
            target_snapshot_arn = response["DBSnapshot"]["DBSnapshotArn"]
            target_engine = response["DBSnapshot"]["Engine"]
            target_engine_version = response["DBSnapshot"]["EngineVersion"]
            waiter = client.get_waiter("db_snapshot_available")
            waiter.wait(
                DBSnapshotIdentifier=target_snapshot, WaiterConfig=get_waiter_config()
            )
    except ClientError as err:
        LOGGER.error(
            "{}: {}".format(
                err.response["Error"]["Code"], err.response["Error"]["Message"]
            )
        )
        return None, None

    return target_snapshot, target_snapshot_arn, target_engine, target_engine_version


def share_snapshot(client, source, target, kms_key, account, cluster_mode):
    source_snapshot_arn = get_latest_snapshot(client, source, cluster_mode)
    if source_snapshot_arn is None:
        LOGGER.error("Failed to get latest DB snapshot")
        return None, None
    now = datetime.now()
    target = target + "-" + now.strftime("%d%M%S")
    LOGGER.info(
        "Updating KMS key of snapshot {} with {}".format(source_snapshot_arn, kms_key)
    )
    (
        target_snapshot,
        target_snapshot_arn,
        target_engine,
        target_engine_version,
    ) = copy_snapshot(client, source_snapshot_arn, target, kms_key, cluster_mode)
    if target_snapshot is None:
        return target_snapshot, target_snapshot_arn

    LOGGER.info("Sharing snapshot {} with {}".format(target_snapshot_arn, account))
    if cluster_mode:
        client.modify_db_cluster_snapshot_attribute(
            DBClusterSnapshotIdentifier=target_snapshot,
            AttributeName="restore",
            ValuesToAdd=[account],
        )
    else:
        client.modify_db_snapshot_attribute(
            DBSnapshotIdentifier=target_snapshot,
            AttributeName="restore",
            ValuesToAdd=[account],
        )

    return target_snapshot, target_snapshot_arn, target_engine, target_engine_version


def restore_snapshot(client, data, target_exists, cluster_mode):
    db_identifier = data["DBIdentifier"]
    temp_identifier = db_identifier + "-new"
    temp_instance_identifier = db_identifier + "-new-main"

    LOGGER.info("Creating RDS {} from {}".format(temp_identifier, data["SnapshotArn"]))
    if cluster_mode:
        LOGGER.info("Creating DB cluster")
        client.restore_db_cluster_from_snapshot(
            DBClusterIdentifier=temp_identifier,
            SnapshotIdentifier=data["SnapshotArn"],
            Engine=data["Engine"],
            EngineVersion=data["EngineVersion"],
            DBClusterInstanceClass=data["DBInstanceClass"],
            DBSubnetGroupName=data["DBSubnetGroupName"],
            VpcSecurityGroupIds=data["VpcSecurityGroupIds"],
            Tags=data["Tags"],
            DeletionProtection=False,
            CopyTagsToSnapshot=True,
            PubliclyAccessible=data["PubliclyAccessible"],
        )
        waiter = client.get_waiter("db_cluster_available")
        waiter.wait(DBClusterIdentifier=temp_identifier, WaiterConfig=get_waiter_config())
        LOGGER.info("Creating DB instance")
        client.create_db_instance(
            DBClusterIdentifier=temp_identifier,
            DBInstanceIdentifier=temp_instance_identifier,
            Engine=data["Engine"],
            DBInstanceClass=data["DBInstanceClass"],
        )
        waiter = client.get_waiter("db_instance_available")
        waiter.wait(
            DBInstanceIdentifier=temp_instance_identifier,
            WaiterConfig=get_waiter_config(),
        )

        if target_exists:
            old_identifier = db_identifier + "-old"
            LOGGER.info("Renaming {} to {}".format(db_identifier, old_identifier))
            client.modify_db_cluster(
                DBClusterIdentifier=db_identifier,
                NewDBClusterIdentifier=old_identifier,
                ApplyImmediately=True,
            )
            waiter = client.get_waiter("db_cluster_available")
            waiter.wait(DBClusterIdentifier=old_identifier, WaiterConfig=get_waiter_config())

        LOGGER.info("Renaming {} to {}".format(temp_identifier, db_identifier))
        client.modify_db_cluster(
            DBClusterIdentifier=temp_identifier,
            NewDBClusterIdentifier=db_identifier,
            ApplyImmediately=True,
        )
        waiter = client.get_waiter("db_cluster_available")
        waiter.wait(DBClusterIdentifier=db_identifier, WaiterConfig=get_waiter_config())

        LOGGER.info("Renaming instance {} to {}".format(temp_instance_identifier, db_identifier + "-main"))
        client.modify_db_instance(
            DBInstanceIdentifier=temp_instance_identifier,
            NewDBInstanceIdentifier=db_identifier + "-main",
            ApplyImmediately=True,
        )
        waiter = client.get_waiter("db_instance_available")
        waiter.wait(
            DBInstanceIdentifier=db_identifier + "-main",
            WaiterConfig=get_waiter_config(),
        )

        if target_exists:
            delete_rds(client, old_identifier, cluster_mode)

    else:
        client.restore_db_instance_from_db_snapshot(
            DBInstanceIdentifier=temp_identifier,
            DBSnapshotIdentifier=data["SnapshotArn"],
            DBInstanceClass=data["DBInstanceClass"],
            DBSubnetGroupName=data["DBSubnetGroupName"],
            PubliclyAccessible=data["PubliclyAccessible"],
            Tags=data["Tags"],
            VpcSecurityGroupIds=data["VpcSecurityGroupIds"],
            CopyTagsToSnapshot=True,
            DeletionProtection=False,
        )
        waiter = client.get_waiter("db_instance_available")
        waiter.wait(
            DBInstanceIdentifier=temp_identifier, WaiterConfig=get_waiter_config()
        )

        if target_exists:
            old_identifier = db_identifier + "-old"
            LOGGER.info("Renaming {} to {}".format(db_identifier, old_identifier))
            client.modify_db_instance(
                DBInstanceIdentifier=db_identifier,
                NewDBInstanceIdentifier=old_identifier,
                ApplyImmediately=True,
            )
            waiter = client.get_waiter("db_instance_available")
            waiter.wait(DBInstanceIdentifier=old_identifier, WaiterConfig=get_waiter_config())

        LOGGER.info("Renaming {} to {}".format(temp_identifier, db_identifier))
        client.modify_db_instance(
            DBInstanceIdentifier=temp_identifier,
            NewDBInstanceIdentifier=db_identifier,
            ApplyImmediately=True,
        )
        waiter = client.get_waiter("db_instance_available")
        waiter.wait(
            DBInstanceIdentifier=db_identifier, WaiterConfig=get_waiter_config()
        )

        if target_exists:
            delete_rds(client, old_identifier, cluster_mode)


def get_snapshot_details(client, snapshot_identifier, cluster_mode):
    """Get snapshot ARN, engine, and engine version by exact snapshot identifier."""
    try:
        if cluster_mode:
            response = client.describe_db_cluster_snapshots(
                DBClusterSnapshotIdentifier=snapshot_identifier
            )
            if not response["DBClusterSnapshots"]:
                LOGGER.error("Snapshot %s not found" % snapshot_identifier)
                return None, None, None, None
            snap = response["DBClusterSnapshots"][0]
            return (
                snap["DBClusterSnapshotIdentifier"],
                snap["DBClusterSnapshotArn"],
                snap["Engine"],
                snap["EngineVersion"],
            )
        else:
            response = client.describe_db_snapshots(
                DBSnapshotIdentifier=snapshot_identifier
            )
            if not response["DBSnapshots"]:
                LOGGER.error("Snapshot %s not found" % snapshot_identifier)
                return None, None, None, None
            snap = response["DBSnapshots"][0]
            return (
                snap["DBSnapshotIdentifier"],
                snap["DBSnapshotArn"],
                snap["Engine"],
                snap["EngineVersion"],
            )
    except ClientError as err:
        LOGGER.error(
            "{}: {}".format(
                err.response["Error"]["Code"], err.response["Error"]["Message"]
            )
        )
        return None, None, None, None


def get_cluster_endpoint(client, db_identifier):
    """Get the writer endpoint of an Aurora cluster."""
    try:
        response = client.describe_db_clusters(DBClusterIdentifier=db_identifier)
        if not response["DBClusters"]:
            return None
        return response["DBClusters"][0]["Endpoint"]
    except ClientError as err:
        LOGGER.error(
            "{}: {}".format(
                err.response["Error"]["Code"], err.response["Error"]["Message"]
            )
        )
        return None


def get_cluster_master_username(client, db_identifier):
    """Get the master username of an Aurora cluster."""
    try:
        response = client.describe_db_clusters(DBClusterIdentifier=db_identifier)
        if not response["DBClusters"]:
            return None
        return response["DBClusters"][0]["MasterUsername"]
    except ClientError as err:
        LOGGER.error(
            "{}: {}".format(
                err.response["Error"]["Code"], err.response["Error"]["Message"]
            )
        )
        return None
