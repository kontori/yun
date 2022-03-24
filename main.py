import base64
import random
import time
import requests
import json
import configparser
import os
from typing import List, Dict

from pyDes import des, CBC, PAD_PKCS5

"""
加密模式：DES/CBC/pkcs5padding
"""
# 偏移量
default_iv = '\1\2\3\4\5\6\7\x08'

# 加载配置文件
cur_path = os.path.dirname(os.path.realpath(__file__))
cfg_path = os.path.join(cur_path, "config.ini")
conf = configparser.ConfigParser()
conf.read(cfg_path, encoding="utf-8")

my_host = conf.get("Yun", "school_host")
default_key = conf.get("Yun", "key")
my_app_edition = conf.get("Yun", "app_edition")

my_token = conf.get("User", 'token')
my_device_id = conf.get("User", "device_id")
my_key = conf.get("User", "map_key")
my_device_name = conf.get("User", "device_name")
my_sys_edition = conf.get("User", "sys_edition")

my_point = conf.get("Run", "point")
min_distance = float(conf.get("Run", "min_distance"))
allow_overflow_distance = float(conf.get("Run", "allow_overflow_distance"))
single_mileage_min_offset = float(conf.get("Run", "single_mileage_min_offset"))
single_mileage_max_offset = float(conf.get("Run", "single_mileage_max_offset"))
cadence_min_offset = int(conf.get("Run", "cadence_min_offset"))
cadence_max_offset = int(conf.get("Run", "cadence_max_offset"))
split_count = int(conf.get("Run", "split_count"))
exclude_points = json.loads(conf.get("Run", "exclude_points"))
min_consume = float(conf.get("Run", "min_consume"))
max_consume = float(conf.get("Run", "max_consume"))


def update():
    conf.write(open(cfg_path, "w+", encoding="utf-8"))


def default_post(router, data, headers=None, m_host=None):
    if m_host is None:
        m_host = my_host
    url = m_host + router
    if headers is None:
        headers = {
            'token': my_token,
            'isApp': 'app',
            'deviceId': my_device_id,
            'version': my_app_edition,
            'platform': 'android',
            'Content-Type': 'text/plain; charset=utf-8',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'okhttp/3.12.0'
        }
    req = requests.post(url=url, data=des_encrypt(data), headers=headers)
    return req.text


def login(user_name, password, school_id, m_type='1'):
    data = {
        'password': password,
        'schoolId': school_id,
        'userName': user_name,
        'type': m_type
    }
    resp = default_post('/login/appLogin', json.dumps(data))
    j = json.loads(resp)
    if j['code'] == 200:
        print("登录成功")
        return j['data']['token']
    else:
        print(j['msg'])
        return ''


def sign_out():
    j = json.loads(default_post("/login/signOut", ""))
    if j['code'] == 200:
        conf.set("Yun", "school_host", "")
        conf.set("User", "token", "")
        update()
        print("退出登录成功")


def school_list():
    yun_host = conf.get("Yun", "yun_host")
    headers = {
        'Content-Type': 'text/plain; charset=utf-8',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': 'okhttp/3.12.0'
    }
    j = json.loads(default_post('/login/schoolList', "", headers=headers, m_host=yun_host))
    if j['code'] == 200:
        for index, item in enumerate(j['data']):
            print(str(index + 1) + "  " + item['schoolName'])
        index = int(input("请输入学校对应编号：")) - 1
        return {
            'schoolId': j['data'][index]['schoolId'],
            'schoolUrl': j['data'][index]['schoolUrl'][:-1]
        }


def des_encrypt(s, key=default_key, iv=default_iv):
    secret_key = key
    k = des(secret_key, CBC, iv, pad=None, padmode=PAD_PKCS5)
    en = k.encrypt(s, padmode=PAD_PKCS5)
    return base64.b64encode(en)


def des_decrypt(s, key=default_key, iv=default_iv):
    secret_key = key
    k = des(secret_key, CBC, iv, pad=None, padmode=PAD_PKCS5)
    de = k.decrypt(base64.b64decode(s), padmode=PAD_PKCS5)
    return de


class Yun:

    def __init__(self):
        data = json.loads(default_post("/run/getHomeRunInfo", ""))['data']['cralist'][0]
        self.raType = data['raType']
        self.raId = data['id']
        self.schoolId = data['schoolId']
        self.raRunArea = data['raRunArea']
        self.raDislikes = data['raDislikes']
        self.raMinDislikes = data['raDislikes']
        self.raSingleMileageMin = data['raSingleMileageMin'] + single_mileage_min_offset
        self.raSingleMileageMax = data['raSingleMileageMax'] + single_mileage_max_offset
        self.raCadenceMin = data['raCadenceMin'] + cadence_min_offset
        self.raCadenceMax = data['raCadenceMax'] + cadence_max_offset
        points = data['points'].split('|')
        print('开始标记打卡点...')
        for exclude_point in exclude_points:
            try:
                points.remove(exclude_point)
                print("成功删除打卡点", exclude_point)
            except ValueError:
                print("打卡点", exclude_point, "不存在")
        self.now_dist = 0
        i = 0
        while (self.now_dist / 1000 > min_distance + allow_overflow_distance) or self.now_dist == 0:
            i += 1
            print('第' + str(i) + '次尝试...')
            self.manageList: List[Dict] = []
            self.now_dist = 0
            self.now_time = 0
            self.task_list = []
            self.task_count = 0
            self.myLikes = 0
            self.generate_task(points)
        self.now_time = int(random.uniform(min_consume, max_consume) * 60 * (self.now_dist / 1000))
        print('打卡点标记完成！本次将打卡' + str(self.myLikes) + '个点，处理' + str(len(self.task_list)) + '个点，总计'
              + format(self.now_dist / 1000, '.2f')
              + '公里，将耗时' + str(self.now_time // 60) + '分' + str(self.now_time % 60) + '秒')
        # 这三个只是初始化，并非最终值
        self.recordStartTime = ''
        self.crsRunRecordId = 0
        self.userName = ''

    def generate_task(self, points):
        random_points = random.sample(points, self.raDislikes)
        for point_index, point in enumerate(random_points):
            if self.now_dist / 1000 < min_distance or self.myLikes < self.raMinDislikes:
                self.manageList.append({
                    'point': point,
                    'marked': 'Y',
                    'index': point_index
                })
                self.add_task(point)
                self.myLikes += 1
            else:
                self.manageList.append({
                    'point': point,
                    'marked': 'N',
                    'index': ''
                })

        if self.now_dist / 1000 < min_distance:
            print('公里数不足' + str(min_distance) + '公里，将自动回跑...')
            index = 0
            while self.now_dist / 1000 < min_distance:
                self.add_task(self.manageList[index]['point'])
                index = (index + 1) % self.raDislikes

    # 每10个路径点作为一组splitPoint;
    # 若最后一组不满10个且多于1个，则将最后一组中每两个点位分取10点（含终点而不含起点），作为一组splitPoint
    # 若最后一组只有1个（这种情况只会发生在len(splitPoints) > 0），则将已插入的最后一组splitPoint的最后一个点替换为最后一组的点
    def add_task(self, point):
        if not self.task_list:
            origin = my_point
        else:
            origin = self.task_list[-1]['originPoint']
        data = {
            'key': my_key,
            'origin': origin,
            'destination': point
        }
        resp = requests.get("https://restapi.amap.com/v4/direction/bicycling", params=data)
        j = json.loads(resp.text)
        split_points = []
        split_point = []
        for path in j['data']['paths']:
            self.now_dist += path['distance']
            path['steps'][-1]['polyline'] += ';' + point
            for step in path['steps']:
                polyline = step['polyline']
                points = polyline.split(';')
                for p in points:
                    split_point.append({
                        'point': p,
                        'runStatus': '1',
                        'speed': format(random.uniform(self.raSingleMileageMin, self.raSingleMileageMax), '.2f')
                    })
                    if len(split_point) == split_count:
                        split_points.append(split_point)
                        self.task_count = self.task_count + 1
                        split_point = []

        if len(split_point) > 1:
            b = split_point[0]['point']
            for i in range(1, len(split_point)):
                new_split_point = []
                a = b
                b = split_point[i]['point']
                a_split = a.split(',')
                b_split = b.split(',')
                a_x = float(a_split[0])
                a_y = float(a_split[1])
                b_x = float(b_split[0])
                b_y = float(b_split[1])
                d_x = (b_x - a_x) / split_count
                d_y = (b_y - a_y) / split_count
                for j in range(0, split_count):
                    new_split_point.append({
                        'point': str(a_x + (j + 1) * d_x) + ',' + str(a_y + (j + 1) * d_y),
                        'runStatus': '1',
                        'speed': format(random.uniform(self.raSingleMileageMin, self.raSingleMileageMax), '.2f')
                    })
                split_points.append(new_split_point)
                self.task_count = self.task_count + 1
        elif len(split_point) == 1:
            split_points[-1][-1] = split_point[0]

        self.task_list.append({
            'originPoint': point,
            'points': split_points
        })

    def start(self):
        data = {
            'raRunArea': self.raRunArea,
            'raType': self.raType,
            'raId': self.raId
        }
        j = json.loads(default_post('/run/start', json.dumps(data)))
        if j['code'] == 200:
            self.recordStartTime = j['data']['recordStartTime']
            self.crsRunRecordId = j['data']['id']
            self.userName = j['data']['studentId']
            print("云运动任务创建成功！")

    def split(self, points):
        data = {
            'cardPointList': points,
            'crsRunRecordId': self.crsRunRecordId,
            'schoolId': self.schoolId,
            'userName': self.userName
        }
        headers = {
            'Content-Type': 'text/plain;charset=utf-8',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'User-Agent': 'okhttp/3.12.0'
        }
        resp = default_post("/run/splitPoints", data=json.dumps(data), headers=headers)
        print('  ' + resp)

    def do(self):
        sleep_time = self.now_time / (self.task_count + 1)
        print('等待' + format(sleep_time, '.2f') + '秒...')
        time.sleep(sleep_time)
        for task_index, task in enumerate(self.task_list):
            print('开始处理第' + str(task_index + 1) + '个点...')
            for split_index, split in enumerate(task['points']):
                self.split(split)
                print('  第' + str(split_index + 1) + '次splitPoint发送成功！等待' + format(sleep_time, '.2f') + '秒...')
                time.sleep(sleep_time)
            print('第' + str(task_index + 1) + '个点处理完毕！')

    def finish(self):
        print('发送结束信号...')
        data = {
            'recordMileage': format(self.now_dist / 1000, '.2f'),
            'recodeCadence': random.randint(self.raCadenceMin, self.raCadenceMax),
            'recodePace': format(self.now_time / 60 / (self.now_dist / 1000), '.2f'),
            'deviceName': my_device_name,
            'sysEdition': my_sys_edition,
            'appEdition': my_app_edition,
            'raIsStartPoint': 'Y',
            'raIsEndPoint': 'Y',
            'raRunArea': self.raRunArea,
            'recodeDislikes': self.myLikes,
            'raId': self.raId,
            'raType': self.raType,
            'id': self.crsRunRecordId,
            'duration': self.now_time,
            'recordStartTime': self.recordStartTime,
            'manageList': self.manageList
        }
        resp = default_post("/run/finish", json.dumps(data))
        print(resp)


if __name__ == '__main__':
    try:
        if my_key == '':
            my_key = input("未能获取高德地图Key。请输入：")
            conf.set("User", "map_key", my_key)
            update()
        if my_device_id == '':
            choice = input("未能获取DeviceId。手动输入？1.输入 2.随机生成\n")
            if choice == '1':
                my_device_id = input("请输入15位DeviceId:")
            else:
                my_device_id = ''.join(str(random.randint(1, 9)) for i in range(15))
                print("生成的DeviceId为：" + my_device_id)
            conf.set("User", "device_id", my_device_id)
            update()
        if my_token == '':
            choice = input("未能获取Token。尝试登录？1.手动输入 2.登录 3.退出\n")
            if choice == '1':
                my_host = input("请先输入学校服务器URL(例如合工大的是http://210.45.246.53:8080，不要少了前面的 http:// ):\n")
                my_token = input("请输入用户Token:")
            elif choice == '2':
                d = school_list()
                my_host = d['schoolUrl']
                s_id = d['schoolId']
                while my_token == '':
                    name = input("请输入学号：")
                    word = input("请输入密码：")
                    my_token = login(name, word, s_id)
            else:
                exit()
            conf.set("Yun", "school_host", my_host)
            conf.set("User", "token", my_token)
            update()
        tmp = json.loads(default_post("/login/getStudentInfo", ""))
        print(tmp['data']['nickName'] + ',信息获取成功！')
        choice = input("1.开始跑步 2.退出登录 3.结束任务\n")
        if choice == '1':
            client = Yun()
            client.start()
            client.do()
            client.finish()
            if input("任务结束！输入yes以退出登录，任意内容结束") == 'yes':
                sign_out()
                input()
        elif choice == '2':
            sign_out()
            input()
    except Exception as e:
        print('任务失败！检查token、高德地图开发者密钥或网络设置')
        print(e)
        input()
