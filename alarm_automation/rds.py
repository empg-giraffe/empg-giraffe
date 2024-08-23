import sys
import os
import math
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from email_sender import EmailSender

class RDSAlarmCreator:
    def __init__(self, session):
        self.INSTANCE_CLASS_SPLIT = 3
        # Assume role 세션 생성
        self.session = session
        self.cloudwatch = self.session.client('cloudwatch', region_name='ap-northeast-2')
        self.rds = self.session.client('rds', region_name='ap-northeast-2')
        self.ec2 = self.session.client('ec2', region_name='ap-northeast-2')        
        # Paginator 생성
        self.rds_clusters_paginator = self.rds.get_paginator('describe_db_clusters')
        self.rds_instances_paginator = self.rds.get_paginator('describe_db_instances')
        self.rds_params_paginator = self.rds.get_paginator('describe_db_parameters')
        self.alarm_paginator = self.cloudwatch.get_paginator('describe_alarms')        
        # 데이터 저장용 리스트
        self.rds_cluster_name = []
        self.rds_instance_name = []
        self.rds_instance_name_not_cluster = []
        self.rds_instance_class = []
        self.rds_instance_memory = []
        self.rds_instance_max_conn = []
        self.rds_instance_storage = []
        self.alarm_arn = {}
        self.alarm_tag = {}        
        # 함수 실행
        self.fetch_rds_cluster_names()
        self.fetch_rds_instance_details()
        self.fetch_alarm_details()                

    # max_conn 계산 함수
    def calculate_max_conn(self, value_expression, memory_bytes):
        try:
            # GREATEST 또는 LEAST 부분 제거하고 내부 표현식 추출
            if value_expression.startswith('GREATEST('):
                expressions = value_expression.replace('GREATEST(', '').rstrip(')').split(',')
                comparison_func = max
            elif value_expression.startswith('LEAST('):
                expressions = value_expression.replace('LEAST(', '').rstrip(')').split(',')
                comparison_func = min
            else:
                expressions = [value_expression]
                comparison_func = max
            results = []
            for expr in expressions:
                expr = expr.strip().strip('{}')
                if 'log(' in expr:
                    # log 함수의 인자 부분 추출
                    log_expr = expr.replace('log(', '').rstrip(')')
                    memory_expr, multiplier = log_expr.split(')*')
                    mem_divisor = int(memory_expr.split('/')[1])
                    log_value = math.log(int(memory_bytes) / mem_divisor)
                    final_value = log_value * int(multiplier)
                    results.append(final_value)
                elif 'DBInstanceClassMemory/' in expr:
                    # DBInstanceClassMemory 나눗셈 표현식 처리
                    mem_divisor = int(expr.split('/')[1])
                    final_value = int(memory_bytes) / mem_divisor
                    results.append(final_value)
                else:
                    try:
                        final_value = int(expr)
                        results.append(final_value)
                    except ValueError:
                        pass            
            return round(comparison_func(results))
        except Exception as e:
            print(f"value_expression '{value_expression}' 처리 중 오류 발생: {e}")
            return None

    def fetch_rds_cluster_names(self):
        for page in self.rds_clusters_paginator.paginate():
            for rds_cluster in page['DBClusters']:
                self.rds_cluster_name.append(rds_cluster['DBClusterIdentifier'])
    
    def fetch_rds_instance_details(self):
        for page in self.rds_instances_paginator.paginate():
            for rds_instance in page['DBInstances']:
                arn = rds_instance['DBInstanceArn']
                tags = self.rds.list_tags_for_resource(ResourceName=arn)['TagList']                
                # Tag Key가 Alert고 Value가 false이면 알람 생성 제외
                skip_instance = any(tag['Key'] == 'Alert' and tag['Value'] == 'false' for tag in tags)
                if skip_instance:
                    continue                
                # 인스턴스 이름 및 유형
                self.rds_instance_name.append(rds_instance['DBInstanceIdentifier'])
                self.rds_instance_class.append(rds_instance['DBInstanceClass'])                
                # 인스턴스 메모리
                instance_type = rds_instance['DBInstanceClass']
                instance_type_info = self.ec2.describe_instance_types(InstanceTypes=[instance_type[self.INSTANCE_CLASS_SPLIT:]])
                for instance_type_detail in instance_type_info['InstanceTypes']:
                    memory_bytes = instance_type_detail['MemoryInfo']['SizeInMiB'] * 1000 * 1000
                    self.rds_instance_memory.append(memory_bytes)                
                # 파라미터 그룹에서 max_connections 값 가져오기
                for param_group in rds_instance['DBParameterGroups']:
                    param_group_name = param_group['DBParameterGroupName']
                    for param_page in self.rds_params_paginator.paginate(DBParameterGroupName=param_group_name):
                        parameters = param_page.get('Parameters', [])
                        for param in parameters:
                            if param.get('ParameterName') == 'max_connections':
                                value_expression = param['ParameterValue']                        
                                try:
                                    max_conn = self.calculate_max_conn(value_expression, memory_bytes)
                                    self.rds_instance_max_conn.append(max_conn)
                                except (ValueError, IndexError) as e:
                                    print(f"value_expression '{value_expression}' 처리 중 오류 발생: {e}")                                    
                # cluster가 아닌 instance의 storage
                if rds_instance.get('DBClusterIdentifier') is None:
                    self.rds_instance_name_not_cluster.append(rds_instance['DBInstanceIdentifier'])
                    self.rds_instance_storage.append(rds_instance['AllocatedStorage'])

    def fetch_alarm_details(self):
        for page in self.alarm_paginator.paginate():
            for alarm in page['MetricAlarms']:
                alarm_name = alarm['AlarmName']
                self.alarm_arn[alarm_name] = alarm['AlarmArn']
                # 태그 값 비교
                tags = self.cloudwatch.list_tags_for_resource(ResourceARN=alarm['AlarmArn'])['Tags']
                instance_class_found = False
                for tag in tags:
                    if tag['Key'] == 'Instance_class':
                        self.alarm_tag[alarm_name] = tag['Value']
                        instance_class_found = True
                        break
                if not instance_class_found:
                    self.alarm_tag[alarm_name] = 'None'

    # CPU Utilization
    def cpu_util(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.rds_cluster_name)):        
            writer_alarm_exists = False
            reader_alarm_exists = False
            writer_alarm_name = '[RDS CPU Utilization] ' + self.rds_cluster_name[x] + ' (writer)'
            reader_alarm_name = '[RDS CPU Utilization] ' + self.rds_cluster_name[x] + ' (reader)'
            for alarm in self.alarm_tag.keys():
                # 동일한 이름의 알람이 있을 때
                if writer_alarm_name == alarm:         
                    print(writer_alarm_name + " already exists")
                    writer_alarm_exists = True
                elif reader_alarm_name == alarm:         
                    print(reader_alarm_name + " already exists")
                    reader_alarm_exists = True
            if not writer_alarm_exists:
                # writer 알람 생성
                print('Creating ' + writer_alarm_name)
                EmailSender.shared_list.append(writer_alarm_name)
                self.cloudwatch.put_metric_alarm(
                        AlarmActions=sns_arn,
                        AlarmName=writer_alarm_name,
                        ComparisonOperator='GreaterThanThreshold',
                        EvaluationPeriods=1,
                        DatapointsToAlarm=1,
                        MetricName='CPUUtilization',
                        Namespace='AWS/RDS',
                        Period=period,
                        Statistic='Maximum',
                        Threshold=threshold,
                        ActionsEnabled=True,
                        AlarmDescription='',
                        Dimensions=[
                            {'Name': 'DBClusterIdentifier','Value': self.rds_cluster_name[x]},
                            {'Name': 'Role','Value': 'WRITER'},
                        ],
                        Tags=[
                            {'Key': 'Org','Value': org},
                            {'Key': 'Env','Value': env},
                            {'Key': 'Name','Value': 'RDS CPU Utilization ' + self.rds_cluster_name[x] + '-writer'}
                        ]
                    )
            if not reader_alarm_exists:
                # reader 알람 생성
                print('Creating ' + reader_alarm_name)
                EmailSender.shared_list.append(reader_alarm_name)
                self.cloudwatch.put_metric_alarm(
                        AlarmActions=sns_arn,
                        AlarmName=reader_alarm_name,
                        ComparisonOperator='GreaterThanThreshold',
                        EvaluationPeriods=1,
                        DatapointsToAlarm=1,
                        MetricName='CPUUtilization',
                        Namespace='AWS/RDS',
                        Period=period,
                        Statistic='Maximum',
                        Threshold=threshold,
                        ActionsEnabled=True,
                        AlarmDescription='',
                        Dimensions=[
                            {'Name': 'DBClusterIdentifier','Value': self.rds_cluster_name[x]},
                            {'Name': 'Role','Value': 'READER'},
                        ],
                        Tags=[
                            {'Key': 'Org','Value': org},
                            {'Key': 'Env','Value': env},
                            {'Key': 'Name','Value': 'RDS CPU Utilization ' + self.rds_cluster_name[x] + '-reader'}
                        ]
                    )            
        for x in range(len(self.rds_instance_name_not_cluster)):        
            instance_alarm_exists = False
            new_alarm_name = '[RDS CPU Utilization] ' + self.rds_instance_name_not_cluster[x]
            for alarm in self.alarm_tag.keys():
                if new_alarm_name == alarm:         
                    print(new_alarm_name + " already exists")
                    instance_alarm_exists = True
            if not instance_alarm_exists:
                print('Creating ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                        AlarmActions=sns_arn,
                        AlarmName=new_alarm_name,
                        ComparisonOperator='GreaterThanThreshold',
                        EvaluationPeriods=1,
                        DatapointsToAlarm=1,
                        MetricName='CPUUtilization',
                        Namespace='AWS/RDS',
                        Period=period,
                        Statistic='Maximum',
                        Threshold=threshold,
                        ActionsEnabled=True,
                        AlarmDescription='',
                        Dimensions=[
                            {'Name': 'DBInstanceIdentifier','Value': self.rds_instance_name_not_cluster[x]},
                        ],
                        Tags=[
                            {'Key': 'Org','Value': org},
                            {'Key': 'Env','Value': env},
                            {'Key': 'Name','Value': 'RDS CPU Utilization ' + self.rds_instance_name_not_cluster[x]}
                        ]                
                    )
    # DatabaseConnections
    def db_conn(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.rds_instance_name)):
            instance_alarm_exists = False
            new_alarm_name = '[RDS DatabaseConnections] ' + self.rds_instance_name[x]
            # 동일한 이름의 알람이 있을때
            if new_alarm_name in self.alarm_tag:
                # 알람 태그와 인스턴스 클래스 비교
                if self.alarm_tag[new_alarm_name] == self.rds_instance_class[x]:
                    instance_alarm_exists = True
                    print(new_alarm_name + " already exists")
                else:
                    instance_alarm_exists = False
                    # print("Creating tag for " + self.rds_instance_name[x])
                    self.cloudwatch.untag_resource(
                        ResourceARN=self.alarm_arn[new_alarm_name],
                        TagKeys=[
                            'Instance_class',
                        ]
                    )
                    self.cloudwatch.tag_resource(
                        ResourceARN=self.alarm_arn[new_alarm_name],
                        Tags=[
                            {'Key': 'Instance_class','Value': self.rds_instance_class[x]},
                        ]
                    )
            else:
                instance_alarm_exists = False        
            if not instance_alarm_exists:
                print('Creating ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='GreaterThanThreshold',
                    EvaluationPeriods=1,
                    DatapointsToAlarm=1,
                    MetricName='DatabaseConnections',
                    Namespace='AWS/RDS',
                    Period=period,
                    Statistic='Maximum',
                    Threshold=round(self.rds_instance_max_conn[x]*threshold/100),
                    ActionsEnabled=True,
                    AlarmDescription='',
                    Dimensions=[
                        {'Name': 'DBInstanceIdentifier','Value': self.rds_instance_name[x]},
                    ],
                    Tags=[
                        {'Key': 'Org','Value': org},
                        {'Key': 'Env','Value': env},
                        {'Key': 'Instance_class','Value': self.rds_instance_class[x]},
                        {'Key': 'Name','Value': 'RDS DatabaseConnections ' + self.rds_instance_name[x]}
                    ]
                )
                
    # FreeableMemory
    def free_mem(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.rds_instance_name)):
            instance_alarm_exists = False
            new_alarm_name = '[RDS FreeableMemory] ' + self.rds_instance_name[x]
            if new_alarm_name in self.alarm_tag:
                if self.alarm_tag[new_alarm_name] == self.rds_instance_class[x]:
                    instance_alarm_exists = True
                    print(new_alarm_name + " already exists")
                else:
                    instance_alarm_exists = False
                    self.cloudwatch.untag_resource(
                        ResourceARN=self.alarm_arn[new_alarm_name],
                        TagKeys=['Instance_class']
                    )
                    self.cloudwatch.tag_resource(
                        ResourceARN=self.alarm_arn[new_alarm_name],
                        Tags=[{'Key': 'Instance_class', 'Value': self.rds_instance_class[x]}]
                    )
            else:
                instance_alarm_exists = False
            if not instance_alarm_exists:
                print('Creating ' + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='LessThanThreshold',
                    EvaluationPeriods=1,
                    DatapointsToAlarm=1,
                    MetricName='FreeableMemory',
                    Namespace='AWS/RDS',
                    Period=period,
                    Statistic='Minimum',
                    Threshold=round(self.rds_instance_memory[x] * threshold / 100),
                    ActionsEnabled=True,
                    AlarmDescription='',
                    Dimensions=[
                        {'Name': 'DBInstanceIdentifier', 'Value': self.rds_instance_name[x]},
                    ],
                    Tags=[
                        {'Key': 'Org', 'Value': org},
                        {'Key': 'Env', 'Value': env},
                        {'Key': 'Instance_class', 'Value': self.rds_instance_class[x]},
                        {'Key': 'Name', 'Value': 'RDS FreeableMemory ' + self.rds_instance_name[x]}
                    ]
                )

    # FreeStorageSpace
    def free_stor(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.rds_instance_name_not_cluster)):
            instance_alarm_exists = False
            new_alarm_name = '[RDS FreeStorageSpace] ' + self.rds_instance_name_not_cluster[x]
            for alarm in self.alarm_tag.keys():
                if new_alarm_name == alarm:         
                    print(new_alarm_name + " already exists")
                    instance_alarm_exists = True
            if not instance_alarm_exists:
                print("Creating " + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
                self.cloudwatch.put_metric_alarm(
                    AlarmActions=sns_arn,
                    AlarmName=new_alarm_name,
                    ComparisonOperator='LessThanThreshold',
                    EvaluationPeriods=1,
                    MetricName='FreeStorageSpace',
                    Namespace='AWS/RDS',
                    Period=period,
                    Statistic='Minimum',
                    Threshold=round(self.rds_instance_storage[x]*threshold/100),
                    ActionsEnabled=True,
                    AlarmDescription='',
                    Dimensions=[
                        {'Name': 'DBInstanceIdentifier','Value': self.rds_instance_name_not_cluster[x]},
                    ],
                    Tags=[
                        {'Key': 'Org','Value': org},
                        {'Key': 'Env','Value': env},
                        {'Key': 'Name','Value': 'RDS FreeStorageSpace ' + self.rds_instance_name_not_cluster[x]}
                    ]   
                )
                
    # VolumeBytesUsed
    def vol_used(self, period, threshold, sns_arn, org, env):
        for x in range(len(self.rds_cluster_name)):
            cluster_alarm_exists = False
            new_alarm_name = '[RDS VolumeBytesUsed] ' + self.rds_cluster_name[x]
            for alarm in self.alarm_tag.keys():
                if new_alarm_name == alarm:         
                    print(new_alarm_name + " already exists")
                    cluster_alarm_exists = True
            if not cluster_alarm_exists:
                print("Creating " + new_alarm_name)
                EmailSender.shared_list.append(new_alarm_name)
            self.cloudwatch.put_metric_alarm(
                AlarmActions=sns_arn,
                AlarmName=new_alarm_name,
                ComparisonOperator='GreaterThanThreshold',
                EvaluationPeriods=1,
                MetricName='VolumeBytesUsed',
                Namespace='AWS/RDS',
                Period=period,
                Statistic='Maximum',
                Threshold=threshold,
                ActionsEnabled=True,
                AlarmDescription='',
                Dimensions=[
                    {'Name': 'DBClusterIdentifier','Value': self.rds_cluster_name[x]},
                ],
                Tags=[
                    {'Key': 'Org','Value': org},
                    {'Key': 'Env','Value': env},
                    {'Key': 'Name','Value': 'RDS VolumeBytesUsed ' + self.rds_cluster_name[x]}
                ]
            )
