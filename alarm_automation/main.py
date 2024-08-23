import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from alb import ALBAlarmCreator
from nlb import NLBAlarmCreator
from ec2 import EC2AlarmCreator
from rds import RDSAlarmCreator
from elasticache import ElasticacheAlarmCreator
from eventbridge import EventbridgeCreator
from email_sender import EmailSender
from variable import account_info
from credentials import assume_session

def alarm():
    for x in range(len(account_info)):
        session = assume_session(account_info[x]['assume_rolearn'])
        account_name = account_info[x]['name']
        
        print("\n" + "********************************************************** Account **********************************************************")
        print(account_info[x]['assume_rolearn'])
        
        # 메일에 포함할 계정 이름
        EmailSender.shared_list.append("************** " + account_name + " **************") 
        
        ########### 함수 인자 순서: period, threshold, sns, org, env ###########
        
        # ALB Alarm
        alb_alarm_creator = ALBAlarmCreator(session)
        alb_alarm_creator.alb_4xx(account_info[x]['alarm_period_1m'], account_info[x]['alb_4xx_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        alb_alarm_creator.alb_5xx(account_info[x]['alarm_period_1m'], account_info[x]['alb_5xx_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        alb_alarm_creator.unhealthy_host(account_info[x]['alarm_period_1m'], account_info[x]['alb_unhealthy_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])

        # NLB_Alarm 
        nlb_alarm_creator = NLBAlarmCreator(session)
        nlb_alarm_creator.unhealthy_host(account_info[x]['alarm_period_1m'], account_info[x]['nlb_unhealthy_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        
        # EC2_Alarm
        ec2_alarm_creator = EC2AlarmCreator(session)
        ec2_alarm_creator.cpu_util(account_info[x]['alarm_period_5m'], account_info[x]['ec2_cpu_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        ec2_alarm_creator.mem_util(account_info[x]['alarm_period_5m'], account_info[x]['ec2_mem_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        ec2_alarm_creator.disk_util(account_info[x]['alarm_period_5m'], account_info[x]['ec2_disk_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])

        # RDS_Alarm
        rds_alarm_creator = RDSAlarmCreator(session)
        rds_alarm_creator.cpu_util(account_info[x]['alarm_period_5m'], account_info[x]['rds_cpu_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        rds_alarm_creator.db_conn(account_info[x]['alarm_period_5m'], account_info[x]['rds_dbconn_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        rds_alarm_creator.free_mem(account_info[x]['alarm_period_5m'], account_info[x]['rds_freemem_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        rds_alarm_creator.vol_used(account_info[x]['alarm_period_5m'], account_info[x]['rds_volused_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])
        rds_alarm_creator.free_stor(account_info[x]['alarm_period_5m'], account_info[x]['rds_freestor_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])

        # Elasticache_Alarm
        elasticache_alarm_creator = ElasticacheAlarmCreator(session)
        elasticache_alarm_creator.cpu_util(account_info[x]['alarm_period_5m'], account_info[x]['elasticache_cpu_thres'], account_info[x]['alarm_sns'], account_info[x]['org'], account_info[x]['env'])

        ########## 함수 인자 rule name ###########

        # EventBridge 
        eventbridge_creator = EventbridgeCreator(session)
        eventbridge_creator.put_rule(account_info[x]['event_rule_name'])
        eventbridge_creator.put_targets(account_info[x]['event_rule_name'], account_info[x]['event_sns'])
        
        if len(EmailSender.shared_list) <= 2:
            EmailSender.shared_list = [" "]
        else:
            for alarm in EmailSender.shared_list:
                EmailSender.result_list.append(alarm)
            EmailSender.shared_list = [" "]
            
            
    # 생성된 알람 리스트를 이메일로 보내는 함수
    email_sender = EmailSender()
    email_sender.send_email(EmailSender.result_list)
