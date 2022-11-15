from datetime import datetime

import boto3
import logging
import utils

LOGGER = logging.getLogger("root")


def init_client(assumed_creds):
    if assumed_creds is None:
        client = boto3.client("rds")
    else:
        client = boto3.client(
            "rds",
            aws_access_key_id=assumed_creds["AccessKeyId"],
            aws_secret_access_key=assumed_creds["SecretAccessKey"],
            aws_session_token=assumed_creds["SessionToken"],
        )
    return client


def target_exists(assumed_creds, target, cluster_mode):
    client = init_client(None)
    if cluster_mode:
        response = rds.describe_db_clusters(
            Filters=[{"Name": "db-cluster-id", "Values": [db_identifier]}]
        )
        if len(response["DBClusters"]) == 0:
            return False

    else:
        response = rds.describe_db_instances(
            Filters=[{"Name": "db-instance-id", "Values": [db_identifier]}]
        )
        if len(response["DBInstances"]) == 0:
            return False
    return True


def get_latest_snapshot(client, db_identifier, cluster_mode):
    if cluster_mode:
        response = client.describe_db_cluster_snapshots(
            DBClusterIdentifier=db_identifier, IncludeShared=True
        )
        if not response["DBClusterSnapshots"]:
            LOGGER.error("Failed to get latest DB snapshot")
            exit(1)
        sorted_keys = sorted(
            response["DBClusterSnapshots"],
            key=itemgetter("SnapshotCreateTime"),
            reverse=True,
        )
        snapshot_arn = sorted_keys[0]["DBClusterSnapshotArn"]
    else:
        response = client.describe_db_snapshots(
            DBInstanceIdentifier=db_identifier, IncludeShared=True
        )
        if not response["DBSnapshots"]:
            LOGGER.error("Failed to get latest DB snapshot")
            exit(1)
        sorted_keys = sorted(
            response["DBSnapshots"], key=itemgetter("SnapshotCreateTime"), reverse=True
        )
        snapshot_arn = sorted_keys[0]["DBSnapshotArn"]
    return snapshot_arn


def get_config(assumed_creds, db_identifier, cluster_mode):
    LOGGER.info("Fetching DB config")
    client = init_client(None)
    security_groups = []
    config = {}

    if cluster_mode:
        response = rds.describe_db_clusters(
            Filters=[{"Name": "db-cluster-id", "Values": [db_identifier]}]
        )
        if len(response["DBClusters"]) > 0:
            db_cluster = response["DBClusters"][0]
            config["availability_zone"] = db_cluster["AvailabilityZone"]
            config["subnet_group"] = db_cluster["DBSubnetGroup"]
            config["tags"] = db_cluster["TagList"]
            vpc_sgs = db_cluster["VpcSecurityGroups"]
            for sg in vpc_sgs:
                security_groups.append(sg["VpcSecurityGroupId"])
    else:
        response = rds.describe_db_instances(
            Filters=[{"Name": "db-instance-id", "Values": [db_identifier]}]
        )
        if len(response["DBInstances"]) > 0:
            db_instance = response["DBInstances"][0]
            config["subnet_group"] = db_instance["DBSubnetGroup"]["DBSubnetGroupName"]
            config["tags"] = db_instance["TagList"]
            config["availability_zone"] = db_instance["AvailabilityZone"]
            vpc_sgs = db_instance["VpcSecurityGroups"]
            for sg in vpc_sgs:
                security_groups.append(sg["VpcSecurityGroupId"])
    logger.info("Security groups: %s" % security_groups)
    logger.info("Availability zone: %s" % availability_zone)
    logger.info("Subnet group: %s" % subnet_group)
    logger.info("Tags: %s" % tags)
    if (
        len(security_groups) == 0
        or len(tags) == 0
        or availability_zone is None
        or subnet_group is None
    ):
        LOGGER.error("Failed to get source DB config")
        exit(1)

    config["security_groups"] = security_groups
    return config


def delete_rds(client, db_identifier, cluster_mode):
    logger.info("Deleting %s db" % db_identifier)
    if cluster_mode:
        client.delete_db_cluster(
            DBClusterIdentifier=db_identifier, SkipFinalSnapshot=True
        )
        waiter = client.get_waiter("db_cluster_deleted")
        waiter.wait(DBClusterIdentifier=db_identifier)

    else:
        client.delete_db_instance(
            DBInstanceIdentifier=db_identifier, SkipFinalSnapshot=True
        )
        waiter = client.get_waiter("db_cluster_available")
        waiter.wait(DBInstanceIdentifier=db_identifier)


def update_identifier(client, source, target, cluster_mode):
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


def load_latest_snapshot(
    client, snapshot_arn, target, target_exists, db_config, cluster_mode
):
    now = datetime.now()
    db_identifier = target
    if target_exists:
        db_identifier = target + "-" + now.strftime("%d%M%S")

    logger.info("Restoring %s snapshot to %s db" % (snapshot_arn, latest_db_identifier))
    if cluster_mode:
        response = client.restore_db_cluster_from_snapshot(
            DBClusterIdentifier=db_identifier,
            SnapshotIdentifier=snapshot_arn,
            AvailabilityZone=config["availability_zone"],
            DBSubnetGroupName=config["subnet_group"],
            VpcSecurityGroupIds=config["security_groups"],
            MultiAZ=False,
            PubliclyAccessible=False,
            AutoMinorVersionUpgrade=False,
            CopyTagsToSnapshot=True,
            Tags=config["tags"],
        )
    else:
        response = client.restore_db_instance_from_db_snapshot(
            DBInstanceIdentifier=db_identifier,
            DBSnapshotIdentifier=snapshot_arn,
            AvailabilityZone=config["availability_zone"],
            DBSubnetGroupName=config["subnet_group"],
            VpcSecurityGroupIds=config["security_groups"],
            MultiAZ=False,
            PubliclyAccessible=False,
            AutoMinorVersionUpgrade=False,
            CopyTagsToSnapshot=True,
            Tags=config["tags"],
        )

    if target_exists:
        delete_rds(client, db_identifier, cluster_mode)

    if cluster_mode:
        waiter = client.get_waiter("db_cluster_available")
        waiter.wait(DBClusterIdentifier=db_identifier)
        if target_exists:
            update_identifier(client, source, target, cluster_mode)
    else:
        waiter = client.get_waiter("db_instance_available")
        waiter.wait(DBInstanceIdentifier=db_identifier)
        if target_exists:
            update_identifier(client, db_identifier, target, cluster_mode)

    return latest_db_identifier


def share_snashot(assumed_creds, source, target, kms_key, account, cluster_mode):
    client = init_client(assumed_creds)
    source_snapshot_arn = get_latest_snapshot(client, source)
    target = target + "-" + now.strftime("%d%M%S")

    if cluster_mode:
        response = client.copy_db_cluster_snapshot(
            SourceDBClusterSnapshotIdentifier=source_snapshot_arn,
            TargetDBClusterSnapshotIdentifier=target,
            KmsKeyId=kms_key,
        )
        target_snapshot_arn = response["DBClusterSnapshots"]["DBClusterSnapshotArn"]
        waiter = client.get_waiter("db_cluster_snapshot_available")
        waiter.wait(DBClusterSnapshotIdentifier=target_snapshot_arn)
        client.modify_db_cluster_snapshot_attribute(
            DBClusterSnapshotIdentifier=target_snapshot_arn,
            AttributeName="restore",
            ValuesToAdd=[account],
        )
    else:
        response = client.copy_db_cluster_snapshot(
            SourceDBClusterSnapshotIdentifier=source_db_identifier,
            TargetDBClusterSnapshotIdentifier=target,
            KmsKeyId=kms_key,
        )
        target_snapshot_arn = response["DBSnapshots"]["DBSnapshotArn"]
        waiter = client.get_waiter("db_snapshot_available")
        waiter.wait(DBSnapshotIdentifier=target_snapshot_arn)
        client.modify_db_snapshot_attribute(
            DBSnapshotIdentifier=target_snapshot_arn,
            AttributeName="restore",
            ValuesToAdd=[account],
        )

    return target


def restore_snashot(
    assumed_creds, source, target, db_config, target_exists, cluster_mode
):
    client = init_client(None)
    utils.validate_db_config(db_config)
    snapshot_arn = get_latest_snapshot(client, source)
    latest_db_identifier = load_latest_snapshot(
        client, snapshot_arn, target, target_exists, db_config, cluster_mode
    )
