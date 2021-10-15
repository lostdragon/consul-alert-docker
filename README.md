## 服务告警

### consul告警服务
对consul健康检查失败的服务，发送企业微信告警。

#### 依赖

- registrator [ https://github.com/lostdragon/registrator ]

registrator 负责注册服务

#### 环境变量

- CONSUL_HOST: consul地址                           
- CONSUL_PORT: consul端口                                 
- KEY: 企业微信机器人webhook key                              
- LOG_PATH: 日志路径                                       
- LOG_FILE： 日志文件名     