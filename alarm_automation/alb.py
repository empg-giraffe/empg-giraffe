import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from email_sender import EmailSender

class ALBAlarmCreator:
    def __init__(self, session):
        # PATH SPLIT 상수
        self.TARGETGROUP_PATH_SPLIT = 5
        self.ELB_PATH_SPLIT = 1
        # Assume role 세션 생성
        self.session = session
        self.cloudwatch = session.client('cloudwatch', region_name='ap-northeast-2')
        self.elb = session.client('elbv2', region_name='ap-northeast-2')
        # Paginator 생성
        self.elb_paginator = self.elb.get_paginator('describe_load_balancers')
        self.tg_paginator = self.elb.get_paginator('describe_target_groups')
        self.alarm_paginator = self.cloudwatch.get_paginator('describe_alarms')
        # ALB 및 TargetGroup 정보 저장용 변수
        self.alb_type = []
        self.alb_name = []
        self.alb_arn = []
        self.tg_arn = []
        self.tg_name = []
        self.tg_elb_arn = []
        self.alarm_name = []
        # ALB,TargetGroup 정보 불러오는 함수 실행
        self.alb_info()
        self.tg_info()
        self.alarm_names()
        
    
    def alb_info(self):
        for albs in self.elb_paginator.paginate():
            for loadbalancers in albs['LoadBalancers']:
                # describe_tags는 paginator 미지원
                alb_tags = self.elb.describe_tags(ResourceArns=[loadbalancers['LoadBalancerArn']])
                # Tag Key가 Alert고 Value가 false이면 알람 생성 제외
                skip_loadbalancer = False
                for alb_tag in alb_tags['TagDescriptions']:
                    for tag in alb_tag['Tags']:
                        if tag['Key'] == 'Alert' and tag['Value'] == 'false':
                            skip_loadbalancer = True
                            break
                    if skip_loadbalancer:
                        break
                if skip_loadbalancer:
                    continue
                # ARN으로 Name, PATH 파싱
                alb_arn_split = loadbalancers['LoadBalancerArn'].split('/', self.ELB_PATH_SPLIT)
                temp_alb_arn = alb_arn_split[1].strip().strip("']\"")
                self.alb_arn.append(temp_alb_arn)
                self.alb_type.append(loadbalancers['Type'])
                self.alb_name.append(loadbalancers['LoadBalancerName'])

    def tg_info(self):
        for tgs in self.tg_paginator.paginate():
            for tg in tgs['TargetGroups']:
                # describe_tags는 paginator 미지원
                tg_tags = self.elb.describe_tags(ResourceArns=[tg['TargetGroupArn']])
                # Tag Key가 Alert고 Value가 false이면 알람 생성 제외
                skip_tg = False
                for tag_desc in tg_tags['TagDescriptions']:
                    for tag in tag_desc['Tags']:
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
                    # 파싱한 ELB가 ALB일때만 append
                    if temp_tg_elb_arn.startswith('app'):
                        self.tg_elb_arn.append(temp_tg_elb_arn)
                        self.tg_arn.append(temp_tg_arn)
                        self.tg_name.append(tg['TargetGroupName'])

    # 알람 중복 제거 위해 현재 알람명 조회                    
    def alarm_names(self):
        for alarm_names in self.alarm_paginator.paginate():
            for name in alarm_names['MetricAlarms']:
                self.alarm_name.append(name['AlarmName'])
    
    def alb_4xx(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.alb_name)):
            new_alarm_name = '[ALB HTTPCode_ELB_4XX_Count] ' + self.alb_name[x]
            # new_alarm_name과 알람명이 같을 경우 continue
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            else:
                # ELB Type이 ALB일 경우에만 알람 생성
                if self.alb_type[x] == 'application':
                    print('Create ' + new_alarm_name)
                    EmailSender.shared_list.append(new_alarm_name)
                    self.cloudwatch.put_metric_alarm(
                        AlarmActions=sns_arn,
                        AlarmName=new_alarm_name,
                        ComparisonOperator='GreaterThanThreshold',
                        EvaluationPeriods=1,
                        MetricName='HTTPCode_ELB_4XX_Count',
                        Namespace='AWS/ApplicationELB',
                        Period=period,
                        Statistic='Sum',
                        Threshold=threshold,
                        ActionsEnabled=True,
                        AlarmDescription='',
                        Dimensions=[
                            {'Name': 'LoadBalancer', 'Value': self.alb_arn[x]},
                        ],
                        Tags=[
                            {'Key': 'Org', 'Value': org},
                            {'Key': 'Env', 'Value': env},
                            {'Key': 'Name', 'Value': 'ALB HTTPCode_ELB_4XX_Count ' + self.alb_name[x]}
                        ]
                    )

    def alb_5xx(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.alb_name)):
            new_alarm_name = '[ALB HTTPCode_ELB_5XX_Count] ' + self.alb_name[x]
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            else:
                if self.alb_type[x] == 'application':
                    print('Create ' + new_alarm_name)
                    EmailSender.shared_list.append(new_alarm_name)
                    self.cloudwatch.put_metric_alarm(
                        AlarmActions=sns_arn,
                        AlarmName=new_alarm_name,
                        ComparisonOperator='GreaterThanThreshold',
                        EvaluationPeriods=1,
                        MetricName='HTTPCode_ELB_5XX_Count',
                        Namespace='AWS/ApplicationELB',
                        Period=period,
                        Statistic='Sum',
                        Threshold=threshold,
                        ActionsEnabled=True,
                        AlarmDescription='',
                        Dimensions=[
                            {'Name': 'LoadBalancer', 'Value': self.alb_arn[x]},
                        ],
                        Tags=[
                            {'Key': 'Org', 'Value': org},
                            {'Key': 'Env', 'Value': env},
                            {'Key': 'Name', 'Value': 'ALB HTTPCode_ELB_5XX_Count ' + self.alb_name[x]}
                        ]
                    )

    def unhealthy_host(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.tg_elb_arn)):
            new_alarm_name = '[ALB UnhealthyHostCount] ' + self.tg_name[x]
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            else:
                print('Create ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='GreaterThanOrEqualToThreshold',
                    EvaluationPeriods=1,
                    MetricName='UnHealthyHostCount',
                    Namespace='AWS/ApplicationELB',
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
                        {'Key': 'Name', 'Value': 'ALB UnHealthyHostCount ' + self.tg_name[x]}
                    ]
                )
