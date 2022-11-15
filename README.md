# Restore RDS snapshot GitHub Action

This is a GitHub action to restore RDS DB snapshot.

[![GitHub Super-Linter](https://github.com/g2crowd/action-aws-db-restore/workflows/Lint%20Code%20Base/badge.svg)](https://github.com/marketplace/actions/super-linter)

## Table of Contents

<!-- toc -->

* [Usage](#usage)
* [Inputs](#inputs)
* [Permissions](#permissions)

<!-- tocstop -->

## Usage
```yaml
    - name: Restore DB snapshot from another account
      uses: g2crowd/aaction-aws-db-restore@main
      with:
        source: my-source
        target: my-target
        delete: true
        cluster: true
        sg: [sg-11, sg-12]
        az: [us-east-1a]
        subnet: my-db-subnet-group
        tags: Name:db-restore,Team:infra
        share: true
        assume: my-iam-role-arn
        key: my-kms-key
        account: 123456789
```

## Inputs

* source (**Required**): The identifier for the source DB snapshot
* target (**Required**): The identifier for the target DB
* delete (**Required**): Whether to delete target DB if exists
* cluster (**Required**): Whether its a DB cluster or not
* sg (_Required if target DB doesn't exists_): A list of Amazon EC2 VPC security groups to associate with this DB
* az (_Required if target DB doesn't exists_): The Availability Zone where the database will be created
* subnet (_Required if target DB doesn't exists_): A DB subnet group to associate with this DB
* tags (_Required if target DB doesn't exists_): Tags to assign to the DB
* share (_Required if target DB doesn't exists_): Whether to share an DB snapshot with another account
* assume (_Required if share is enabled_): IAM role to be assumed for sharing DB
* key (_Required if share is enabled_): The Amazon Web Services KMS key identifier for an encrypted DB snapshot
* account (_Required if share is enabled_): Id of the target AWS account

## Permissions

This action requires the following minimum set of permissions:

```json
{
  "Version":"2012-10-17",
  "Statement":[
    {
      "Sid":"SnapshotRestoreAccess",
      "Action":[
        "rds:DescribeDBInstances",
        "rds:DescribeDBClusters",
        "rds:CreateDBInstance",
        "rds:CreateDBCluster",
        "rds:DescribeDBSnapshots",
        "rds:DescribeDBClusterSnapshots",
        "rds:RestoreDBInstanceFromDBSnapshot",
        "rds:RestoreDBClusterFromSnapshot	"
      ],
      "Effect":"Allow",
      "Resource":[
        "*"
      ]
    },
    {
      "Sid":"SnapshotRestoreWriteAccess",
      "Action":[
        "rds:DeleteDBInstance",
        "rds:DeleteDBCluster",
        "rds:ModifyDBInstance",
        "rds:ModifyDBCluster"
      ],
      "Effect":"Allow",
      "Resource":[
        "*"
      ],
      "Condition":{
        "ForAllValues:StringEquals":{
          "rds:db-tag/AllowWrites":[
            "True"
          ]
        }
      }
    },
    {
      "Sid":"SnapshotShareAccess",
      "Action":[
        "rds:CopyDBClusterSnapshot",
        "rds:CopyDBSnapshot",
        "rds:ModifyDBClusterSnapshotAttribute",
        "rds:ModifyDBSnapshotAttribute"
      ],
      "Effect":"Allow",
      "Resource":[
        "*"
      ],
      "Condition":{
        "ForAllValues:StringEquals":{
          "rds:db-tag/AllowWrites":[
            "True"
          ]
        }
      }
    }
  ]
}
```
