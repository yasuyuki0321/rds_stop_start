import boto3
import datetime
import distutils.util
import jpholiday
import logging
import os
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ['REGION']
# リージョン単位の指定
AUTO_STOP = os.environ['AUTO_STOP']
AUTO_START = os.environ['AUTO_START']
STOP_HOLIDAY = os.environ['STOP_HOLIDAY']
# インスタンスの指定
NO_STOP_TAG = os.environ['NO_STOP_TAG']
NO_START_TAG = os.environ['NO_START_TAG']

rds = boto3.client('rds', region_name=REGION)


# 対象のRDSのリストの作成だけを行うフラグを返す
def only_check_target_rds(event):
    logger.info("start function: {}".format(sys._getframe().f_code.co_name))

    list_flag = False
    for key, val in event.items():
        if key == "LIST" and val == "True":
            list_flag = True
    return list_flag


# 自動起動/停止の設定確認
def check_auto_stop_start(action):
    logger.info("start function: {}".format(sys._getframe().f_code.co_name))

    auto_stop_start = True
    if action == 'STOP' and AUTO_STOP == 'False':
        auto_stop_start = False
    elif action == 'START' and AUTO_START == 'False':
        auto_stop_start = False

    logger.info('AUTO_STOP/AUTO_START: {}'.format(auto_stop_start))
    return auto_stop_start


# 対象のRDSのリストを作成
def get_target_rds(action):
    logger.info("start function: {}".format(sys._getframe().f_code.co_name))

    if action == "STOP":
        status = 'available'
    elif action == "START":
        status = 'stopped'

    rds_instance_list = []
    for rds_instance in rds.describe_db_instances()['DBInstances']:
        if rds_instance['DBInstanceStatus'] == status:
            rds_instance_list.append(
                {'id': rds_instance['DBInstanceIdentifier'], 'arn': rds_instance['DBInstanceArn']})
    return rds_instance_list


# RDSのタグを取得
def get_rds_tags(rds_instance):
    logger.info("start function: {}".format(sys._getframe().f_code.co_name))

    tag_list = rds.list_tags_for_resource(
        ResourceName=rds_instance['arn'])['TagList']
    logger.info('rds_id: {} tags: {}'. format(rds_instance['id'], tag_list))
    return tag_list


# RDSの停止/起動
def change_rds_status(action, rds_id):
    logger.info("start function: {}".format(sys._getframe().f_code.co_name))

    if action == 'STOP':
        result = rds.stop_db_instance(DBInstanceIdentifier=rds_id)
        logger.info("rds stop command result: {}" .format(result))
    elif action == 'START':
        result = rds.start_db_instance(DBInstanceIdentifier=rds_id)
        logger.info("rds start command result: {}".format(result))
    return result


# 土日祝日の判定
def is_holiday():
    logger.info("start function: {}".format(sys._getframe().f_code.co_name))

    today = datetime.date.today() + datetime.timedelta(days=0)
    logger.info('today: {}'.format(today))
    return jpholiday.is_holiday(today)


# メインの処理
def lambda_handler(event, context):
    logger.info("start lambda function: {}".format(context.function_name))

    try:
        return_values = {}
        rds_instances = []
        list_flag = only_check_target_rds(event)

        if distutils.util.strtobool(STOP_HOLIDAY):
            holiday_flag = is_holiday()
            logging.info('is_holiday: {}'.format(holiday_flag))

            if holiday_flag:
                return return_values

        if 'ACTION' not in event:
            raise KeyError("The key [ACTION] does not exist in event.")
        action = event['ACTION']
        logger.info('action: {}'.format(action))

        if action not in ["STOP", "START"]:
            raise KeyError("action must be one of [STOP, START]")

        if not check_auto_stop_start(action):
            return return_values

        rds_instance_list = get_target_rds(action)
        logger.info('rds_instance_list: {}'.format(rds_instance_list))

        for rds_instance in rds_instance_list:
            no_action_flg = False
            rds_tags = get_rds_tags(rds_instance)

            for rds_tag in rds_tags:
                if action == 'STOP' and rds_tag['Key'] == NO_STOP_TAG and rds_tag['Value'] == 'True':
                    no_action_flg = True
                    logger.info(
                        'rds_id: {} no_stop_tag: {}'.format(
                            rds_instance['id'], no_action_flg))

                elif action == 'START' and rds_tag['Key'] == NO_START_TAG and rds_tag['Value'] == 'True':
                    no_action_flg = True
                    logger.info(
                        'rds_id: {} no_start_tag: {}'.format(
                            rds_instance['id'], no_action_flg))

            if list_flag is True:
                if no_action_flg is False:
                    logger.info(
                        'action: {} rds_id: {}'.format(
                            action, rds_instance['id']))
                    rds_instances.append(rds_instance['id'])
            elif no_action_flg is False:
                change_rds_status(action, rds_instance['id'])
                rds_instances.append(rds_instance['id'])
            else:
                logger.info(
                    'no action for rds_id: {}'.format(
                        rds_instance['id']))

        if len(rds_instances) == 0:
            logger.info('no target rds')
        else:
            logger.info('action: {} targte: {}'.format(action, rds_instances))

        return_values['rds_instance'] = rds_instances
        return return_values

    except Exception as e:
        logger.error("error ocured {}".format(e))
        return_values['error_desc'] = str(e)
        return return_values
