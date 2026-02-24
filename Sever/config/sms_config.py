# 阿里云 AccessKey（建议改用环境变量；此处仅作本地调试备用）
ACCESS_KEY_ID = ""
ACCESS_KEY_SECRET = ""

# 阿里云号码认证服务 API 端点（一般不需要改）
ENDPOINT = "dypnsapi.aliyuncs.com"

# 短信签名（必填，在阿里云控制台申请）
SIGN_NAME = "速通互联验证码"

# 短信模板编码（必填，在阿里云控制台申请）
TEMPLATE_CODE = "100001"

# 方案名称（可选，不填则使用默认方案）
SCHEME_NAME = None

# 国家码（默认 86 = 中国大陆）
COUNTRY_CODE = "86"

# 验证码有效期（分钟，默认 5）
MINUTES = 5

# 发送频控间隔（秒，同一手机号两次发送的最小间隔，默认 60）
INTERVAL = 60

# 验证码长度（4~8，默认 6）
CODE_LENGTH = 6

# 验证码类型（1=纯数字，默认 1）
CODE_TYPE = 1

# 模板变量名：验证码（模板内占位符名称，如 ${code}，默认 code）
CODE_PARAM_NAME = "code"

# 模板变量名：有效期分钟数（模板内占位符名称，如 ${min}，默认 min）
MIN_PARAM_NAME = "min"