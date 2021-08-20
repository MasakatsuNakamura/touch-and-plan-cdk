from aws_cdk import core as cdk

# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
from aws_cdk import core

from aws_cdk import (
  aws_s3 as s3,
  aws_ec2 as ec2,
  aws_ecs as ecs,
  aws_ecs_patterns as ecsp,
  aws_ecr as ecr,
  aws_elasticloadbalancingv2 as alb,
  core as cdk,
)
import os

class TouchAndPlanCdkStack(cdk.Stack):

  def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
    super().__init__(scope, construct_id, **kwargs)

    # The code that defines your stack goes here
    # bucket = s3.Bucket(self,
    #   "MyFirstBucket",
    #   versioned=True,)

    cidr = '10.1.0.0/16'
    vpc = ec2.Vpc(
      self,
      id='touch-and-plan-vpc',
      cidr=cidr,
      subnet_configuration=[
        ec2.SubnetConfiguration(
          cidr_mask=20,
          name='public',
          subnet_type=ec2.SubnetType.PUBLIC,
        ),
      ],
    )

    cluster = ecs.Cluster(
      self,
      id='touch-and-plan-cluster',
      cluster_name='touch-and-plan-cluster',
      vpc=vpc,
    )

    ecr_web = ecr.Repository(
      self,
      'ecr_web',
      repository_name='touch_and_plan_web',
    )
    ecr_nginx = ecr.Repository(
      self,
      'ecr_nginx',
      repository_name='touch_and_plan_nginx',
    )
    ecr_geojson = ecr.Repository(
      self,
      'ecr_geojson',
      repository_name='touch_and_plan_geojson',
    )

    # load_balancer = alb.ApplicationLoadBalancer(
    #   self,
    #   id='touch_and_plan_alb',
    #   vpc=vpc,
    # )

    # ecsp.ApplicationLoadBalancedFargateService(
    #   self,
    #   "Touch&Plan Web",
    #   task_image_options=ecsp.ApplicationLoadBalancedTaskImageOptions(
    #     image=ecs.ContainerImage.from_registry("nginx")
    #   ),
    #   public_load_balancer=True,
    # )

    task_definition_touch_and_plan = ecs.TaskDefinition(
      self,
      id='touch-and-plan',
      compatibility=ecs.Compatibility('FARGATE'),
      cpu='256',
      memory_mib='512',
      family='touch-and-plan',
    )

    task_definition_touch_and_plan.add_container(
      id='nginx',
      image=ecs.ContainerImage.from_ecr_repository(ecr_nginx),
    )

    task_definition_touch_and_plan.add_container(
      id='web',
      image=ecs.ContainerImage.from_ecr_repository(ecr_web),
    )

    task_definition_geojson = ecs.TaskDefinition(
      self,
      id='geojson',
      compatibility=ecs.Compatibility('FARGATE'),
      cpu='256',
      memory_mib='512',
      family='geojson',
    )

    task_definition_geojson.add_container(
      id='nginx',
      image=ecs.ContainerImage.from_ecr_repository(ecr_geojson),
    )

    ecs.FargateService(
      self,
      id='service-touch-and-plan',
      service_name='touch-and-plan',
      desired_count=0,
      cluster=cluster,
      task_definition=task_definition_touch_and_plan,
    )

    ecs.FargateService(
      self,
      id='service-geojson',
      service_name='geojson',
      desired_count=0,
      cluster=cluster,
      task_definition=task_definition_geojson,
    )

    # security_group = ec2.SecurityGroup(
    #   self,
    #   id='test-security-group',
    #   vpc=vpc,
    #   security_group_name='test-security-group'
    # )

    # security_group.add_ingress_rule(
    #   peer=ec2.Peer.ipv4(cidr),
    #   connection=ec2.Port.tcp(22),
    # )

    # image_id = ec2.AmazonLinuxImage(generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2).get_image(self).image_id

    # ec2.CfnInstance(
    #   self,
    #   id='testec2',
    #   availability_zone="ap-northeast-1a",
    #   image_id=image_id,
    #   instance_type="t3.micro",
    #   key_name='testkey',
    #   security_group_ids=[security_group.security_group_id],
    #   subnet_id=vpc.private_subnets[0].subnet_id,
    #   tags=[{
    #     "key": "Name",
    #     "value": "testec2"
    #   }]
    # )
