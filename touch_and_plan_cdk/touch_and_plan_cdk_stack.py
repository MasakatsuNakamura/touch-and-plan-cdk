from socket import timeout
from aws_cdk import core as cdk

# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
from aws_cdk import core

from aws_cdk import (
  aws_s3 as s3,
  aws_iam as iam,
  aws_ec2 as ec2,
  aws_ecs as ecs,
  aws_ecr as ecr,
  aws_elasticloadbalancingv2 as alb,
  aws_route53 as route53,
  aws_route53_targets as alias,
  aws_certificatemanager as acm,
  aws_rds as rds,
  aws_logs as logs,
  core as cdk,
)

from cdk_ec2_key_pair import KeyPair

class TouchAndPlanCdkStack(cdk.Stack):

  def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
    super().__init__(scope, construct_id, **kwargs)

    # The code that defines your stack goes here
    app_name = 'touch-and-plan'
    cidr = '10.1.0.0/16'

    bucket = s3.Bucket(self,
      "S3Bucket",
      bucket_name=f"{app_name}-bucket",
      versioned=True,)

    bucket_staging = s3.Bucket(self,
      "S3BucketStaging",
      bucket_name=f"{app_name}-staging-bucket",
      versioned=True,)

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

    vpc_tp = ec2.Vpc.from_lookup(self, id='TPPlannerVPC',
      vpc_id='vpc-076934b9cd5f7038a',
    )

    vpc_peering_connection = ec2.CfnVPCPeeringConnection(self, 'Peering',
      vpc_id=cdk.Token.as_string(vpc.vpc_id),
      peer_vpc_id=cdk.Token.as_string(vpc_tp.vpc_id),
    )

    for i, subnet in enumerate(vpc.public_subnets):
      ec2.CfnRoute(self, f'VpcRoute{i}',
        route_table_id=subnet.route_table.route_table_id,
        destination_cidr_block=vpc_tp.vpc_cidr_block,
        vpc_peering_connection_id=vpc_peering_connection.ref,
      )

    for i, subnet in enumerate(vpc_tp.select_subnets().subnets):
      ec2.CfnRoute(self, f'PeerVpcRoute{i}',
        route_table_id=subnet.route_table.route_table_id,
        destination_cidr_block=vpc.vpc_cidr_block,
        vpc_peering_connection_id=vpc_peering_connection.ref,
      )

    ec2_security_group = ec2.SecurityGroup(
      self,
      id='ec2-security-group',
      vpc=vpc,
      security_group_name='ec2-security-group'
    )

    ec2_security_group.add_ingress_rule(peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(22))
    ec2_security_group.add_ingress_rule(peer=ec2.Peer.ipv4(cidr), connection=ec2.Port.tcp(80))

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

    task_role = iam.Role(self, "TaskRole",
      assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      role_name=f'{"".join(s.capitalize() for s in app_name.split("-"))}TaskRole',
    )

    task_role.add_to_policy(iam.PolicyStatement(
      resources=["*"],
      actions=["ssm:CreateActivation", "iam:PassRole"],
    ))

    task_role.add_to_policy(iam.PolicyStatement(
      resources=[bucket.bucket_arn],
      actions=["s3:List*"],
    ))

    task_role.add_to_policy(iam.PolicyStatement(
      resources=[f'{bucket.bucket_arn}/*'],
      actions=["s3:Get*", "s3:Put*", "s3:Delete*"],
    ))

    task_role.add_to_policy(iam.PolicyStatement(
      resources=[bucket_staging.bucket_arn],
      actions=["s3:List*"],
    ))

    task_role.add_to_policy(iam.PolicyStatement(
      resources=[f'{bucket_staging.bucket_arn}/*'],
      actions=["s3:Get*", "s3:Put*", "s3:Delete*"],
    ))

    task_definition = ecs.FargateTaskDefinition(
      self,
      id='touch-and-plan',
      cpu=256,
      memory_limit_mib=512,
      family=app_name,
      task_role=task_role,
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

    ecs_security_group = ec2.SecurityGroup(
      self,
      "ECSSecurityGroup",
      vpc=vpc,
      security_group_name=f'{app_name}-ecs-sg',
    )

    ecs_service = ecs.FargateService(
      self,
      id='service-touch-and-plan',
      service_name=app_name,
      desired_count=0,
      cluster=cluster,
      task_definition=task_definition,
      security_group=ecs_security_group,
      vpc_subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
      assign_public_ip=True,
    )

    logs.LogGroup(
      self,
      id='LogGroup',
      log_group_name=f'/ecs/{app_name}',
      removal_policy=cdk.RemovalPolicy.DESTROY,
    )

    # ステージング環境のECSサービスを定義
    task_definition_stg = ecs.FargateTaskDefinition(
      self,
      id='touch-and-plan-staging',
      execution_role=task_definition.execution_role,
      cpu=256,
      memory_limit_mib=512,
      family=f"{app_name}-staging",
      task_role=task_role,
    )

    container = task_definition_stg.add_container(
      id='nginx',
      image=ecs.ContainerImage.from_ecr_repository(ecr_nginx),
    )

    container.add_port_mappings(ecs.PortMapping(container_port=80, host_port=80))

    task_definition_stg.add_container(
      id='web',
      image=ecs.ContainerImage.from_ecr_repository(ecr_web),
    )

    ecs_service_stg = ecs.FargateService(
      self,
      id='service-touch-and-plan-staging',
      service_name=f"{app_name}-staging",
      desired_count=0,
      cluster=cluster,
      task_definition=task_definition_stg,
      security_group=ecs_security_group,
      vpc_subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
      assign_public_ip=True,
    )

    logs.LogGroup(
      self,
      id='LogGroupStg',
      log_group_name=f'/ecs/{app_name}-staging',
      removal_policy=cdk.RemovalPolicy.DESTROY,
    )

    alb_security_group = ec2.SecurityGroup(
      self,
      "ALBSecurityGroup",
      vpc=vpc,
      security_group_name=f'{app_name}-alb-sg',
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

    load_balancer.set_attribute('idle_timeout.timeout_seconds', '300')

    hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
      self,
      'hosted-zone',
      zone_name='tasuki-tech.jp',
      hosted_zone_id='Z01510561ZAO0Y6YTTFNY',
    )

    route53.ARecord(self, "ARecord",
      zone=hosted_zone,
      target=route53.RecordTarget.from_alias(alias.LoadBalancerTarget(load_balancer)),
      record_name=app_name,
    )

    route53.ARecord(self, "ARecordWild",
      zone=hosted_zone,
      target=route53.RecordTarget.from_alias(alias.LoadBalancerTarget(load_balancer)),
      record_name=f"*.{app_name}",
    )

    certificate = acm.Certificate(
      self,
      "Certificate",
      domain_name="touch-and-plan.tasuki-tech.jp",
      validation=acm.CertificateValidation.from_dns(hosted_zone)
    )

    certificate_wild = acm.Certificate(
      self,
      "CertificateWild",
      domain_name="*.touch-and-plan.tasuki-tech.jp",
      validation=acm.CertificateValidation.from_dns(hosted_zone)
    )

    listener = load_balancer.add_listener(
      "Listner",
      port=443,
      open=True,
      certificates=[certificate, certificate_wild],
    )

    # 本番サービスのリスナーを追加
    listener.add_targets(
      "ECS",
      port=80,
      targets=[ecs_service.load_balancer_target(
        container_name="nginx",
        container_port=80
      )],
      target_group_name=f'{app_name}-tg'
    )

    # ステージングサービスのリスナーを追加
    listener.add_targets(
      "ECSStg",
      port=80,
      conditions=[
        alb.ListenerCondition.host_headers([f"staging.{app_name}.tasuki-tech.jp"]),
      ],
      priority=100,
      targets=[ecs_service_stg.load_balancer_target(
        container_name="nginx",
        container_port=80
      )]
    )

    # Non-SSLのリスナーを追加(SSLに転送する)
    listener_80 = load_balancer.add_listener(
      "NonSslListener",
      port=80,
      open=True,
    )

    listener_80.add_redirect_response(
      "RedirectResponse",
      status_code="HTTP_301",
      protocol='HTTPS',
      host='#{host}',
      port='443',
      path='/#{path}',
      query='#{query}',
    )

    rds_security_group = ec2.SecurityGroup(
      self,
      "RDSSecurityGroup",
      vpc=vpc,
      security_group_name=f'{app_name}-rds-sg',
    )

    rds_security_group.add_ingress_rule(ecs_security_group, ec2.Port.tcp(3306))
    rds_security_group.add_ingress_rule(ec2_security_group, ec2.Port.tcp(3306))

    parameter_group = rds.ParameterGroup(
      self,
      "ParameterGroup",
      engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_25),
      parameters={
        "character_set_client": "utf8mb4",
        "character_set_connection": "utf8mb4",
        "character_set_database": "utf8mb4",
        "character_set_results": "utf8mb4",
        "character_set_server": "utf8mb4",
        "innodb_file_per_table": "1",
        "skip-character-set-client-handshake": "1",
        "init_connect": "SET NAMES utf8mb4",
        "sort_buffer_size": "8388608",
      },
      description=f'{app_name} Parameter Group',
    )

    # 本番環境用RDSインスタンスを作成
    # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
    rds.DatabaseInstance(self, "Instance",
      engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_25),
      instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.SMALL), # optional, defaults to m5.large
      credentials=rds.Credentials.from_generated_secret('admin', secret_name=app_name), # Optional - will default to 'admin' username and generated password
      parameter_group=parameter_group,
      vpc=vpc,
      vpc_subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
      security_groups=[rds_security_group],
      database_name=app_name.replace("-", "_"),
      instance_identifier=f'{app_name}-rds',
      storage_encrypted=True,
      backup_retention=cdk.Duration.days(7),
      monitoring_interval=cdk.Duration.seconds(60),
      cloudwatch_logs_retention=logs.RetentionDays.ONE_MONTH,
      auto_minor_version_upgrade=False,
    )

    # ステージング環境用RDSインスタンスを作成
    rds.DatabaseInstance(self, "InstanceStg",
      engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_25),
      instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.SMALL), # optional, defaults to m5.large
      credentials=rds.Credentials.from_generated_secret('admin', secret_name=f"{app_name}-staging"), # Optional - will default to 'admin' username and generated password
      parameter_group=parameter_group,
      vpc=vpc,
      vpc_subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
      security_groups=[rds_security_group],
      database_name=f"{app_name}-staging".replace("-", "_"),
      instance_identifier=f'{app_name}-staging-rds',
      storage_encrypted=True,
      backup_retention=cdk.Duration.days(7),
      monitoring_interval=cdk.Duration.seconds(60),
      cloudwatch_logs_retention=logs.RetentionDays.ONE_MONTH,
      auto_minor_version_upgrade=False,
    )

    key_pair = KeyPair(
      self,
      "KeyPair",
      name=f'{app_name}',
      store_public_key=True,
    )

    user_data = ec2.UserData.for_linux(shebang='#!/bin/bash -ex exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&')
    user_data.add_commands('yum update -y')
    user_data.add_commands('yum localinstall -y https://dev.mysql.com/get/mysql80-community-release-el7-3.noarch.rpm')
    user_data.add_commands('yum-config-manager --enable mysql80-community')
    user_data.add_commands('yum install -y mysql-community-client')
    user_data.add_commands('amazon-linux-extras install nginx1 -y')
    user_data.add_commands('echo "server {" > /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  listen  80;" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  server_name  heroz-dev.touch-and-plan.tasuki-tech.jp;" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  location / {" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "    proxy_pass https://calc-volume-dev.heroz.jp;" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  }" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "}" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "server {" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  listen  80;" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  server_name  heroz.touch-and-plan.tasuki-tech.jp;" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  location / {" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "    proxy_pass https://calc-volume.heroz.jp;" > /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "  }" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('echo "}" >> /etc/nginx/conf.d/app.conf')
    user_data.add_commands('systemctl start nginx')
    user_data.add_commands('systemctl enable nginx')

    ec2.Instance(
      self,
      'ec2',
      vpc=vpc,
      machine_image=ec2.AmazonLinuxImage(generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2),
      instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO),
      key_name=key_pair.key_pair_name,
      security_group=ec2_security_group,
      vpc_subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
      user_data=user_data,
      instance_name=f'{app_name} Bastion',
    )
