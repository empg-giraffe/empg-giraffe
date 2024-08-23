import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from email_sender import EmailSender

class EC2AlarmCreator:
    def __init__(self, session):
        # Assume role 세션 생성
        self.session = session
        self.cloudwatch = self.session.client('cloudwatch', region_name='ap-northeast-2')
        self.ec2 = self.session.client('ec2', region_name='ap-northeast-2')
        # Paginator 생성
        self.ec2_paginator = self.ec2.get_paginator('describe_instances')
        self.alarm_paginator = self.cloudwatch.get_paginator('describe_alarms')
        self.metric_paginator = self.cloudwatch.get_paginator('list_metrics')
        # EC2 정보 저장용 변수
        self.only_name_tag = []
        self.instance_id = []
        self.instance_state = []
        self.alarm_name = []
        # EC2 정보 불러오는 함수 실행
        self.instance_tag()
        self.alarm_names()

    def instance_tag(self):
        for instances in self.ec2_paginator.paginate():
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    name_tag = None
                    eks_tag = None
                    skip_instance = False
                    # Tag Key가 Alert고 Value가 false이면 알람 생성 제외
                    for tag in instance.get('Tags', []):
                        instance_ids = instance['InstanceId']
                        if tag['Key'] == 'Alert' and tag['Value'] == 'false':
                            skip_instance = True
                            break
                        if tag['Key'] == 'Name':
                            name_tag = tag['Value']
                        if tag['Key'] == 'aws:eks:cluster-name':
                            eks_tag = tag['Value']
                    # EKS Node, Alert Tag가 있을 경우 알람 생성 제외
                    if not eks_tag and name_tag and not skip_instance:
                        self.only_name_tag.append(name_tag)
                        self.instance_id.append(instance_ids)
                        self.instance_state.append(instance['State']['Name'])
                        
    # 알람 중복 제거 위해 현재 알람명 조회
    def alarm_names(self):
        for alarm_names in self.alarm_paginator.paginate():
            for name in alarm_names['MetricAlarms']:
                self.alarm_name.append(name['AlarmName'])

    def cpu_util(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.only_name_tag)):
            # Instance 상태가 stopped이면 continue
            if self.instance_state[x] == 'stopped':
                continue
            # new_alarm_name과 알람명이 같을 경우 continue
            new_alarm_name = '[EC2 CPU Utilization] ' + self.only_name_tag[x]
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            else:
                print('Create ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='GreaterThanThreshold',
                    EvaluationPeriods=1,
                    MetricName='CPUUtilization',
                    Namespace='AWS/EC2',
                    Period=period,
                    Statistic='Maximum',
                    Threshold=threshold,
                    ActionsEnabled=True,
                    AlarmDescription='',
                    Dimensions=[{'Name': 'InstanceId', 'Value': self.instance_id[x]}],
                    Tags=[
                        {'Key': 'Org', 'Value': org},
                        {'Key': 'Env', 'Value': env},
                        {'Key': 'Name', 'Value': 'EC2 CPU Utilization ' + self.only_name_tag[x]}
                    ]
                )

    def mem_util(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.only_name_tag)):
            if self.instance_state[x] == 'stopped':
                continue
            new_alarm_name = '[EC2 Memory Utilization] ' + self.only_name_tag[x]
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            else:
                print('Create ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='GreaterThanThreshold',
                    EvaluationPeriods=1,
                    MetricName='mem_used_percent',
                    Namespace='CWAgent',
                    Period=period,
                    Statistic='Maximum',
                    Threshold=threshold,
                    ActionsEnabled=True,
                    AlarmDescription='',
                    Dimensions=[{'Name': 'InstanceId', 'Value': self.instance_id[x]}],
                    Tags=[
                        {'Key': 'Org', 'Value': org},
                        {'Key': 'Env', 'Value': env},
                        {'Key': 'Name', 'Value': 'EC2 Memory Utilization ' + self.only_name_tag[x]}
                    ]
                )

    def disk_util(self, period, threshold, sns_arn, org, env):
        metric_paginator = self.cloudwatch.get_paginator('list_metrics')
        for cloudwatch_metric in self.metric_paginator.paginate(Namespace='CWAgent', MetricName='disk_used_percent'):
            for metric in cloudwatch_metric['Metrics']:
                instance_id = None
                mount_path = None
                # cloudwatch agent가 설치된 인스턴스만 알람 생성
                for dimension in metric['Dimensions']:
                    if dimension['Name'] == 'InstanceId':
                        instance_id = dimension['Value']
                    if dimension['Name'] == 'path':
                        mount_path = dimension['Value']
                # 마운트 Path 별로 알람 생성
                if instance_id and (mount_path == '/' or mount_path == '/prometheus'):
                    for instance_names in self.ec2.get_paginator('describe_instances').paginate(InstanceIds=[instance_id]):
                        for reservation in instance_names['Reservations']:
                            for instance_name in reservation['Instances']:
                                if 'Tags' in instance_name:
                                    for tag in instance_name['Tags']:
                                        if tag['Key'] == 'Name':
                                            nametag = tag['Value']
                                            new_alarm_name = '[EC2 Disk Utilization] ' + nametag + '-' + mount_path
                                            if new_alarm_name in self.alarm_name:
                                                print(new_alarm_name + " already exists")
                                                continue
                                            else:
                                                print('Create ' + new_alarm_name)
                                                EmailSender.shared_list.append(new_alarm_name)
                                                self.cloudwatch.put_metric_alarm(
                                                    AlarmActions=sns_arn,
                                                    AlarmName=new_alarm_name,
                                                    ComparisonOperator='GreaterThanThreshold',
                                                    EvaluationPeriods=1,
                                                    MetricName='disk_used_percent',
                                                    Namespace='CWAgent',
                                                    Period=period,
                                                    Statistic='Maximum',
                                                    Threshold=threshold,
                                                    ActionsEnabled=True,
                                                    AlarmDescription='Disk utilization alarm for EC2 instance',
                                                    Dimensions=metric['Dimensions'],
                                                    Tags=[
                                                        {'Key': 'Org', 'Value': org},
                                                        {'Key': 'Env', 'Value': env},
                                                        {'Key': 'Name', 'Value': 'EC2 Disk Utilization ' + nametag + '-' + mount_path}
                                                    ]
                                                )
