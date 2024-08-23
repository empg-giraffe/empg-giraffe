import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from email_sender import EmailSender

class NLBAlarmCreator:
    def __init__(self, session):
        self.TARGETGROUP_PATH_SPLIT = 5
        self.ELB_PATH_SPLIT = 1
        # Assume role 세션 생성
        self.session = session
        self.cloudwatch = self.session.client('cloudwatch', region_name='ap-northeast-2')
        self.elb = self.session.client('elbv2', region_name='ap-northeast-2')
        # Paginator 생성
        self.tg_paginator = self.elb.get_paginator('describe_target_groups')
        self.alarm_paginator = self.cloudwatch.get_paginator('describe_alarms')
        # TargetGroup 정보 저장용 변수
        self.tg_arn = []
        self.tg_name = []
        self.tg_elb_arn = []
        self.alarm_name = []
        # TargetGroup 정보 불러오는 함수 실행
        self.tg_info()
        self.alarm_names()
    
    def tg_info(self):
        for tgs in self.tg_paginator.paginate():
            for tg in tgs['TargetGroups']:
                tg_tags = self.elb.describe_tags(ResourceArns=[tg['TargetGroupArn']])
                skip_tg = False
                for tg_tag in tg_tags['TagDescriptions']:
                    for tag in tg_tag['Tags']:
                        # Tag Key가 Alert고 Value가 false이면 알람 생성 제외
                        if tag['Key'] == 'Alert' and tag['Value'] == 'false':
                            skip_tg = True
                            break
                    if skip_tg:
                        break
                if skip_tg:
                    continue
                # ARN으로 Name, PATH 파싱
                tg_elb_arn_split = str(tg['LoadBalancerArns']).split('/', self.ELB_PATH_SPLIT)
                tg_arn_split = tg['TargetGroupArn'].split(':', self.TARGETGROUP_PATH_SPLIT)
                # TargetGroup이 ELB에 할당되어 있을때만 파싱 및 알람 생성
                if len(tg_elb_arn_split) > 1:
                    temp_tg_elb_arn = tg_elb_arn_split[1].strip().strip("']\"")
                    temp_tg_arn = tg_arn_split[5].strip().strip("']\"")
                    if temp_tg_elb_arn.startswith('net'):
                        self.tg_elb_arn.append(temp_tg_elb_arn)
                        self.tg_arn.append(temp_tg_arn)
                        self.tg_name.append(tg['TargetGroupName'])
    
    # 알람 중복 제거 위해 현재 알람명 조회 
    def alarm_names(self):
        for alarm_names in self.alarm_paginator.paginate():
            for name in alarm_names['MetricAlarms']:
                self.alarm_name.append(name['AlarmName'])
    
    def unhealthy_host(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.tg_arn)):
            # new_alarm_name과 알람명이 같을 경우 continue
            new_alarm_name = '[NLB UnhealthyHostCount] ' + self.tg_name[x]
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            print('Creat ' + new_alarm_name)
            EmailSender.shared_list.append(new_alarm_name)
            self.cloudwatch.put_metric_alarm(
                AlarmActions=sns_arn,
                AlarmName=new_alarm_name,
                ComparisonOperator='GreaterThanOrEqualToThreshold',
                EvaluationPeriods=1,
                MetricName='UnHealthyHostCount',
                Namespace='AWS/NetworkELB',
                Period=period,
                Statistic='Minimum',
                Threshold=threshold,
                ActionsEnabled=True,
                AlarmDescription='',
                Dimensions=[
                    {'Name': 'LoadBalancer', 'Value': self.tg_elb_arn[x]},
                    {'Name': 'TargetGroup', 'Value': self.tg_arn[x]}
                ],
                Tags=[
                    {'Key': 'Org', 'Value': org},
                    {'Key': 'Env', 'Value': env},
                    {'Key': 'Name', 'Value': 'NLB UnhealthyHostCount ' + self.tg_name[x]}
                ]
            )
