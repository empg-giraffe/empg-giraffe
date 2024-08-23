import boto3

def assume_session(role_arn):
    sts = boto3.client('sts', region_name='ap-northeast-2')
    assume = sts.assume_role(RoleArn=role_arn, RoleSessionName='session')
    credentials = assume['Credentials']
    assume_role = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name = 'ap-northeast-2'
    )
    return assume_role
