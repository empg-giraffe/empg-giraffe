import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from email_sender import EmailSender

class ElasticacheAlarmCreator:
    def __init__(self, session):
        # Assume role 세션 생성
        self.session = session
        self.elasticache = self.session.client('elasticache', region_name='ap-northeast-2')
        self.cloudwatch = self.session.client('cloudwatch', region_name='ap-northeast-2')
        
        # Paginator 생성
        self.redis_paginator = self.elasticache.get_paginator('describe_cache_clusters')
        self.alarm_paginator = self.cloudwatch.get_paginator('describe_alarms')

        self.redis_name = []
        self.alarm_name = []

        self.redis_names()
        self.alarm_names()

    def redis_names(self):
        for redis in self.redis_paginator.paginate():
            for cluster in redis['CacheClusters']:
                tags = self.elasticache.list_tags_for_resource(ResourceName=cluster['ARN'])
                skip_cluster = False
                # Tag Key가 Alert고 Value가 false이면 알람 생성 제외
                for tag in tags['TagList']:
                    if tag['Key'] == 'Alert' and tag['Value'] == 'false':
                        skip_cluster = True
                        break
                if skip_cluster:
                    continue
                self.redis_name.append(cluster['CacheClusterId'])

    # 알람 중복 제거 위해 현재 알람명 조회
    def alarm_names(self):
        for alarm_names in self.alarm_paginator.paginate():
            for name in alarm_names['MetricAlarms']:
                self.alarm_name.append(name['AlarmName'])

    def cpu_util(self, period, threshold, sns_arn, org, env):
        for name in self.redis_name:
            # new_alarm_name과 알람명이 같을 경우 continue
            new_alarm_name = '[Elasticache CPU Utilization] ' + name
            if new_alarm_name in self.alarm_name:
                print(new_alarm_name + " already exists")
                continue
            else:
                print('Creating ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='GreaterThanThreshold',
                    EvaluationPeriods=1,
                    MetricName='CPUUtilization',
                    Namespace='AWS/ElastiCache',
                    Period=period,
                    Statistic='Maximum',
                    Threshold=threshold,
                    ActionsEnabled=True,
                    AlarmDescription='',
                    Dimensions=[{'Name': 'CacheClusterId', 'Value': name}],
                    Tags=[
                        {'Key': 'Org', 'Value': org},
                        {'Key': 'Env', 'Value': env},
                        {'Key': 'Name', 'Value': 'Elasticache CPU Utilization ' + name}
                    ]
                )
