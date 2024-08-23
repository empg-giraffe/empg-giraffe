import sys
import os
import datetime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'alarm_automation')))
from airflow.utils.dates import days_ago
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from main import alarm
 
default_args = {
    'owner': 'inc',
    'depends_on_past': False,
    'start_date': days_ago(n=1),
    'email_on_failure': False,
    'email_on_retry': False,
}
 
dag = DAG(
    'alarm-automation',
    default_args=default_args,
    description='alarm-automation',
    schedule_interval='00 00 * * *', 
)
 
task_alarm = PythonOperator(
    task_id='alarm_task',
    python_callable=alarm,
    dag=dag,
)
 
task_alarm 
 
dag
