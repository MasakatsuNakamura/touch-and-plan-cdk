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
  aws_route53 as route53,
  aws_certificatemanager as acm,
  aws_rds as rds,
  aws_ssm as ssm,
  aws_logs as logs,
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

    app_name = 'touch-and-plan'

    cidr = '10.1.0.0/16'
    vpc = ec2.Vpc(
      self,
      id='touch-and-plan-vpc',
      cidr=cidr,
      nat_gateways=1,
      subnet_configuration=[
        ec2.SubnetConfiguration(
          cidr_mask=20,
          name='public',
          subnet_type=ec2.SubnetType.PUBLIC,
        ),
        ec2.SubnetConfiguration(
          cidr_mask=20,
          name='private',
          subnet_type=ec2.SubnetType.PRIVATE,
        ),
      ],
    )

    cluster = ecs.Cluster(
      self,
      id='touch-and-plan-cluster',
      cluster_name=f'{app_name}-cluster',
      vpc=vpc,
    )

    ecr_web = ecr.Repository(
      self,
      'ecr_web',
      repository_name=f'{app_name}-web',
      removal_policy=cdk.RemovalPolicy.DESTROY,
    )
    ecr_nginx = ecr.Repository(
      self,
      'ecr_nginx',
      repository_name=f'{app_name}-nginx',
      removal_policy=cdk.RemovalPolicy.DESTROY,
    )
    ecr_geojson = ecr.Repository(
      self,
      'ecr_geojson',
      repository_name=f'{app_name}-geojson',
      removal_policy=cdk.RemovalPolicy.DESTROY,
    )

    task_definition = ecs.FargateTaskDefinition(
      self,
      id='touch-and-plan',
      cpu=256,
      memory_limit_mib=512,
      family=app_name,
    )

    container = task_definition.add_container(
      id='nginx',
      image=ecs.ContainerImage.from_ecr_repository(ecr_nginx),
    )

    container.add_port_mappings(ecs.PortMapping(container_port=80, host_port=80))

    task_definition.add_container(
      id='web',
      image=ecs.ContainerImage.from_ecr_repository(ecr_web),
    )

    task_definition.add_container(
      id='geojson',
      image=ecs.ContainerImage.from_ecr_repository(ecr_geojson),
    )

    ecs_service = ecs.FargateService(
      self,
      id='service-touch-and-plan',
      service_name=app_name,
      desired_count=0,
      cluster=cluster,
      task_definition=task_definition,
    )

    logs.LogGroup(
      self,
      id='LogGroup',
      log_group_name=f'/ecs/{app_name}',
      removal_policy=cdk.RemovalPolicy.DESTROY,
    )

    alb_security_group = ec2.SecurityGroup(
      self,
      "ALBSecurityGroup",
      vpc=vpc,
    )

    alb_security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
    alb_security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))

    load_balancer = alb.ApplicationLoadBalancer(
      self,
      id='load-balancer',
      load_balancer_name=f'{app_name}-alb',
      vpc=vpc,
      internet_facing=True,
      security_group=alb_security_group,
    )

    hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
      self,
      'hosted-zone',
      zone_name='tasuki-tech.jp',
      hosted_zone_id='Z01510561ZAO0Y6YTTFNY',
    )

    certificate = acm.Certificate(
      self,
      "Certificate",
      domain_name="touch-and-plan.tasuki-tech.jp",
      validation=acm.CertificateValidation.from_dns(hosted_zone)
    )

    listener = load_balancer.add_listener(
      "Listner",
      port=443,
      open=True,
      certificates=[certificate],
    )

    listener.add_targets(
      "ECS",
      port=80,
      targets=[ecs_service.load_balancer_target(
        container_name="nginx",
        container_port=80
      )],
      target_group_name=f'{app_name}-tg'
    )

    rds_security_group = ec2.SecurityGroup(
      self,
      "RDSSecurityGroup",
      vpc=vpc,
    )

    rds_security_group.add_ingress_rule(ec2.Peer.ipv4(cidr), ec2.Port.tcp(3306))

    rds_credentials = rds.Credentials.from_generated_secret('admin', secret_name=app_name)
    # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
    rds_instance = rds.DatabaseInstance(self, "Instance",
      engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_25),
      credentials=rds_credentials,
      # optional, defaults to m5.large
      instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.SMALL),
      # credentials=rds.Credentials.from_generated_secret("syscdk"), # Optional - will default to 'admin' username and generated password
      vpc=vpc,
      vpc_subnets={
        "subnet_type": ec2.SubnetType.PRIVATE
      },
      security_groups=[rds_security_group],
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
