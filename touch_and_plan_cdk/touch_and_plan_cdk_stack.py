from aws_cdk import core as cdk

# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
from aws_cdk import core

from aws_cdk import (
  aws_s3 as s3,
  aws_ec2 as ec2,
  core as cdk
)

class TouchAndPlanCdkStack(cdk.Stack):

  def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
    super().__init__(scope, construct_id, **kwargs)

    # The code that defines your stack goes here
    bucket = s3.Bucket(self,
      "MyFirstBucket",
      versioned=True,)

    cidr = '10.0.0.0/21'
    vpc = ec2.Vpc(
      self,
      id='test-vpc',
      cidr=cidr,
      nat_gateways=1,
      subnet_configuration=[
        ec2.SubnetConfiguration(
          cidr_mask=24,
          name='public',
          subnet_type=ec2.SubnetType.PUBLIC,
        ),
        ec2.SubnetConfiguration(
          cidr_mask=24,
          name='private',
          subnet_type=ec2.SubnetType.PRIVATE,
        ),
      ],
    )

    security_group = ec2.SecurityGroup(
      self,
      id='test-security-group',
      vpc=vpc,
      security_group_name='test-security-group'
    )

    security_group.add_ingress_rule(
      peer=ec2.Peer.ipv4(cidr),
      connection=ec2.Port.tcp(22),
    )

    image_id = ec2.AmazonLinuxImage(generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2).get_image(self).image_id

    ec2.CfnInstance(
      self,
      id='testec2',
      availability_zone="ap-northeast-1a",
      image_id=image_id,
      instance_type="t3.micro",
      key_name='testkey',
      security_group_ids=[security_group.security_group_id],
      subnet_id=vpc.private_subnets[0].subnet_id,
      tags=[{
        "key": "Name",
        "value": "testec2"
      }]
    )