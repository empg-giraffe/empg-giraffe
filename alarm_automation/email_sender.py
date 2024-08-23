import boto3
from datetime import datetime

class EmailSender:
    
    shared_list = [" "]
    result_list = []
    
    def __init__(self):
        self.ses = boto3.client('ses', region_name='ap-northeast-2')
        self.current_datetime = datetime.today().strftime("%Y-%m-%d")
    
    # 알람 목록 리스트를 문자열로 변경
    def list_to_str(self, items, delimiter="<br>"):
        return delimiter.join(map(str, items))

    # 이메일 발송
    def send_email(self, items):
        if len(items) > 0:
            response = self.ses.send_email(
                Destination={
                    "ToAddresses": ["msp-support@shinsegae.com"],
                },
                Message={
                    "Body": {
                        "Html": {
                            "Charset": "UTF-8",
                            "Data": "<h3>" + "아래 Cloudwatch 알람이 생성되었습니다." + "</h3>" + "<p>" + self.list_to_str(items) + "</p>"
                        }
                    },
                    "Subject": {
                        "Charset": "UTF-8",
                        "Data": "[알림] Cloudwatch 알람이 생성되었습니다. (" + str(self.current_datetime) + ")"
                    },
                },
                Source="msp-support@shinsegae.com"
            )
            return response
        else:
            pass
