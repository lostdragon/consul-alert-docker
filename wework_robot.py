import base64
import hashlib
import logging

import requests

DEBUG = False
LOGGER = logging.getLogger()


class MessageType(object):
    TEXT = 'text'  # 文本类型。对应消息的限制：文本内容，最长不超过2048个字节，必须是utf8编码
    MARKDOWN = 'markdown'  # markdown类型,对应消息内容限制：markdown内容，最长不超过4096个字节，必须是utf8编码
    IMAGE = 'image'  # 图片，对应图片的base64编码限制：图片（base64编码前）最大不能超过2M，支持JPG,PNG格式
    NEWS = 'news'  # 图文消息，限制：图文消息，一个图文消息支持1到8条图文


class WeworkRobotException(Exception):
    pass


class Message(object):

    def __init__(self):
        self.msg_type = MessageType.TEXT
        self.content = ''
        self.mentioned_list = None
        self.mentioned_mobile_list = None
        self.image_path = None
        self.articles = []

    def set_text(self, content):
        """

        :param content: 文本内容，最长不超过2048个字节，必须是utf8编码
        :type content:
        :return:
        :rtype:
        """
        self.msg_type = MessageType.TEXT
        self.content = content
        return self

    def set_markdown(self, content):
        """

        :param content: markdown内容，最长不超过4096个字节，必须是utf8编码
        :type content:
        :return:
        :rtype:
        """
        self.msg_type = MessageType.MARKDOWN
        self.content = content
        return self

    def set_mentioned_list(self, mentioned_list):
        """

        :param mentioned_list: userid的列表，提醒群中的指定成员(@某个成员)，@all表示提醒所有人，如果开发者获取不到userid，可以使用mentioned_mobile_list
        :type mentioned_list:
        :return:
        :rtype:
        """
        assert isinstance(mentioned_list, list)
        self.mentioned_list = mentioned_list
        return self

    def set_mentioned_mobile_list(self, mentioned_mobile_list):
        """

        :param mentioned_mobile_list: 手机号列表，提醒手机号对应的群成员(@某个成员)，@all表示提醒所有人(该参数只在消息类型为text的时候有效)
        :type mentioned_mobile_list:
        :return:
        :rtype:
        """

        assert isinstance(mentioned_mobile_list, list)
        self.mentioned_mobile_list = mentioned_mobile_list
        return self

    def set_image_path(self, image_path):
        """

        图片（base64编码前）最大不能超过2M，支持JPG,PNG格式
        :param image_path:
        :type image_path:
        :return:
        :rtype:
        """
        self.image_path = image_path
        self.msg_type = MessageType.IMAGE
        return self

    def add_article(self, title, description, url, picurl):
        """

        :param title: 标题，不超过128个字节，超过会自动截断
        :type title:
        :param description: 描述，不超过512个字节，超过会自动截断
        :type description:
        :param url: 点击后跳转的链接。
        :type url:
        :param picurl: 图文消息的图片链接，支持JPG、PNG格式，较好的效果为大图 1068*455，小图150*150。
        :type picurl:
        :return:
        :rtype:
        """
        self.msg_type = MessageType.NEWS

        if len(self.articles) > 8:
            raise WeworkRobotException('article exceed max')

        self.articles.append({
            'title': title,
            'description': description,
            'url': url,
            'picurl': picurl
        })

        return self

    def payload(self):
        body = {
            "msgtype": self.msg_type,
            self.msg_type: {}
        }

        if self.msg_type in [MessageType.TEXT, MessageType.MARKDOWN]:
            body[self.msg_type]['content'] = self.content

        if self.msg_type == MessageType.TEXT:
            if self.mentioned_list:
                body[self.msg_type]['mentioned_list'] = self.mentioned_list
            if self.mentioned_mobile_list:
                body[self.msg_type]['mentioned_mobile_list'] = self.mentioned_mobile_list

        elif self.msg_type == MessageType.IMAGE:
            with open(self.image_path, "rb") as f:
                content = f.read()
                # 转化图片的base64
                base64_content = base64.b64encode(content)
                # 计算图片的md5
                fmd5 = hashlib.md5(content)
            body[self.msg_type].update({"base64": base64_content.decode('utf8'), "md5": fmd5.hexdigest()})

        elif self.msg_type == MessageType.NEWS:
            body[self.msg_type]['articles'] = self.articles

        return body


class WeworkRobot(object):
    """

    每个机器人发送的消息不能超过20条/分钟。

    """
    headers = {
        "Content-Type": "application/json"
    }
    response_message = {
        "errcode": 1,
        "errmessage": ""
    }

    def __init__(self, key):
        self.url = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={}'.format(key)

    def send(self, message):
        body = message.payload()

        if DEBUG:
            LOGGER.info('url = {}, body = {}'.format(self.url, body))
            return self.response_message
        else:
            try:
                response = requests.post(self.url, json=body, headers=self.headers, timeout=10)
                if response.status_code == 200 and response.json()["errcode"] == 0:
                    return self.response_message  # 发送成功
                else:
                    # 发送失败
                    return {
                        "errcode": 0,
                        "errmessage": str(response.json())
                    }
            except Exception as e:
                # 请求失败
                return {
                    "errcode": 0,
                    "errmessage": str(e)
                }


if __name__ == '__main__':
    print(Message().set_text('text').set_mentioned_list(['test1', 'test2']).set_mentioned_mobile_list(
        ['13800001111']).payload())

    import datetime

    service = 'test'
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    header = '<font color="warning">{}</font>出现异常，请相关同事注意。'.format(service)
    color = "warning"
    dc = 'dc1'
    node = 'consul-client-new-prod-python01'
    state = 'critical'
    check_id = 'service:new-prod-python01:openapi_www_1:8073'
    output = 'Get http://10.50.30.5:8073/: dial tcp 10.50.30.5:8073: connect: connection refused'
    markdown = ('{header}\n'
                '>Time: <font color="comment">{time}</font>\n'
                '>DC: <font color="comment">{dc}</font>\n'
                '>Node: <font color="comment">{node}</font>\n'
                '>Service: {service}\n'
                '>State: <font color="{color}">{state}</font>\n'
                '>CheckID: <font color="comment">{check_id}</font>\n'
                '>Output:\n\n{output}').format(
        header=header, time=now, dc=dc, node=node, service=service,
        color=color, state=state, check_id=check_id,
        output=output)

    message = Message().set_markdown(markdown)

    print(Message().set_image_path('./requirements.txt').payload())

    print(Message().add_article("中秋节礼品领取", "今年中秋节公司有豪礼相送", "www.qq.com",
                                "http://res.mail.qq.com/node/ww/wwopenmng/images/independent/doc/test_pic_msg1.png").payload())

    print(WeworkRobot("8312d634-bad7-4a44-b8bf-51e9e0779667").send(message))
