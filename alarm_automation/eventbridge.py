import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

class EventbridgeCreator:
    def __init__(self, session):
        self.SNS_NAME_SPLIT = 5
        self.session = session
        self.eventbridge = self.session.client('events', region_name='ap-northeast-2')
    
    # 규칙 생성
    def put_rule(self, event_rule_name):
        self.eventbridge.put_rule( 
            Name= event_rule_name,
            EventPattern= '{  "source": ["aws.config"],  "detail-type": ["Config Configuration Item Change"],  "detail": {    "messageType": ["ConfigurationItemChangeNotification"],    "configurationItem": {      "configurationItemStatus":["OK", "ResourceDeleted", "ResourceDiscovered"],      "resourceType": ["AWS::EC2::RouteTable", "AWS::EC2::SubnetRouteTableAssociation"]    }  }}' , 
            State= 'ENABLED' , 
        ) 

    # 규칙이 트리거될 때 호출하는 대상
    def put_targets(self, event_rule_name, event_sns):
        event_sns_name = event_sns.split(':')[self.SNS_NAME_SPLIT]
        self.eventbridge.put_targets( 
            Rule= event_rule_name,
            Targets=[ 
                { 
                    'Id' : event_sns_name, 
                    'Arn' : event_sns , 
                }, 
            ] 
        )
