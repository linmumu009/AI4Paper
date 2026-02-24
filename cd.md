cd /
cd /projects/ArxivPaper4/View

\# 验证 cwd 正常
pwd
ls -la package.json

\# 再装依赖
npm install

chmod +x node_modules/.bin/vite

===============================

cd Sever

uvicorn api:app --reload --port 8000


好的，这里是您从更新 Python 版本开始的操作顺序列表：

1. 检查是否可以使用 `dnf` 安装 Python 3.11：

   ```bash
   sudo dnf list python3.11
   ```

2. 检查当前系统默认的 Python 版本：

   ```bash
   python3 --version
   ```

3. 将系统默认的 Python 版本切换为 Python 3.11：

   ```bash
   sudo alternatives --set python3 /usr/bin/python3.11
   ```

4. 再次检查 Python 版本以确认更新成功：

   ```bash
   python3 --version
   ```

5. 检查是否可以使用 `dnf` 安装 `python3-pip`：

   ```bash
   sudo dnf list python3-pip
   ```

6. 验证 `pip` 是否可以正常使用：

   ```bash
   python3 -m pip --version
   ```

7. 查找 `pip` 的可执行文件路径：

   ```bash
   find /usr -name "pip*" -type f 2>/dev/null
   ```

8. 创建符号链接以便直接使用 `pip` 命令：

   ```bash
   sudo ln -s /usr/local/bin/pip3.11 /usr/local/bin/pip
   ```

9. 验证 `pip` 命令是否可以正常使用：

   ```bash
   pip --version
   ```

10. 升级 `pip` 到最新版本：

    ```bash
    python3.11 -m pip install --upgrade pip
    ```

11. pip install -r requirements.txt
12. pip install python-multipart
13. uvicorn api:app --reload --port 8000

=====================================

cd View

npm install

npm run dev

# 长期运行

很好，你的 `uvicorn` 路径已经确定是 **`/usr/local/bin/uvicorn`**，所以 systemd 的 `ExecStart` 可以直接用我给的模板，不用猜。

我按你现在目录和启动方式，给你一套**完全对得上**的最终版（并且解决“关掉远程连接就掉”的问题）。

------

## 一、先把后端做成 systemd（开机自启 + 不会掉）

### 1）创建服务文件

```bash
vi /etc/systemd/system/arxiv-api.service
```

粘贴下面这一份（路径已按你机器对齐）：

```ini
[Unit]
Description=ArxivPaper4 FastAPI (uvicorn)
After=network.target

[Service]
WorkingDirectory=/projects/ArxivPaper4/Sever
User=root
Group=root

ExecStart=/usr/local/bin/uvicorn api:app --host 127.0.0.1 --port 8000 --workers 2

Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

> 说明：
>
> - 监听 `127.0.0.1`：只允许本机访问，外网必须走 Nginx，更安全
> - `--workers 2`：简单提升并发；如果机器小可以改 1

### 2）启动并设为自启

```bash
systemctl daemon-reload
systemctl enable --now arxiv-api
systemctl status arxiv-api --no-pager
```

看日志（如果启动失败最有用）：

```bash
journalctl -u arxiv-api -n 200 --no-pager
```

------

## 二、前端不要再用 vite dev（dev 会话一断就没）

上线建议：**build 静态文件 + Nginx 托管**

### 1）构建 dist

```bash
cd /projects/ArxivPaper4/View
npm install
chmod +x node_modules/.bin/vite
chmod +x node_modules/.bin/tsc
chmod +x node_modules/typescript/bin/tsc
npm run build
ls -la dist
nginx -t
systemctl reload nginx

cd /projects/ArxivPaper4/Mobile
npm install
chmod +x node_modules/.bin/vite
chmod +x node_modules/.bin/tsc
chmod +x node_modules/typescript/bin/tsc
npm run build
ls -la dist
nginx -t
systemctl reload nginx
```

------

## 三、Nginx：托管前端 + 反代后端 /api

### 1）安装并启动 nginx

```bash
yum install -y nginx
systemctl enable --now nginx
```

### 2）写 Nginx 配置

```bash
vi /etc/nginx/conf.d/arxivpaper4.conf
```

粘贴：

```nginx
server {
    listen 80;
    server_name _;

    # 桌面端默认站点
    root /projects/ArxivPaper4/View/dist;
    index index.html;

    # 移动端静态资源（配合 Mobile 构建 base=/m/）
    location /m/assets/ {
        alias /projects/ArxivPaper4/Mobile/dist/assets/;
    }

    # 移动端 SPA 路由
    location /m/ {
        alias /projects/ArxivPaper4/Mobile/dist/;
        try_files $uri $uri/ /m/index.html;
    }

    location = /m/index.html {
        alias /projects/ArxivPaper4/Mobile/dist/index.html;
    }

    # 桌面端 SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # /api/xxx -> http://127.0.0.1:8000/xxx
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # /static/xxx -> http://127.0.0.1:8000/static/xxx (PDF.js viewer, kb_files, data)
    location /static/ {
        proxy_pass http://127.0.0.1:8000/static/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

测试并重载：

```bash
nginx -t
systemctl reload nginx
```

------

## 四、开放端口（阿里云安全组）

上线后你只需要开放：

- ✅ **80**（HTTP）
- （可选）✅ **443**（HTTPS）

不要开放 5173/8000（除非你就是要临时调试）。

------

## 五、验证是否正常

在服务器本机：

```bash
curl -I http://127.0.0.1
curl -I http://127.0.0.1/m/
curl -I http://127.0.0.1/m/assets/
curl -I http://127.0.0.1/api
```

在你电脑浏览器：

- `http://公网IP/`（前端）
- `http://公网IP/api/...`（后端接口）

------

## 一个你很可能会遇到的点：前端接口地址

如果你前端写死了 `http://127.0.0.1:8000` 或 `http://localhost:8000`，上线后必须改成：

- **推荐**：同域 `/api/xxx`

这样就不需要 CORS，也最省事。

------

## 如果你暂时还想“开发模式”但不断线就不掉（临时方案）

不用改架构，直接 tmux：

```bash
yum install -y tmux
tmux new -s arxiv
```

里面开两个窗格分别跑：

```bash
cd /projects/ArxivPaper4/View
npm run dev -- --host 0.0.0.0 --port 5173
cd /projects/ArxivPaper4/Sever
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

离开 tmux：`Ctrl+b` 然后 `d`

------

你现在想一步到位“上线稳定可长期跑”，还是先用 tmux 解决不断线问题再慢慢上线？我建议直接走 **systemd + nginx**（上面这套就是）。如果你执行过程中某一步报错，把 `systemctl status arxiv-api` 和 `journalctl -u arxiv-api -n 50` 的输出贴我，我可以直接定位到哪一行要改。



# 更新流程

# 后端更新后
systemctl restart arxiv-api

# 前端更新后


cd /projects/ArxivPaper4/View
npm install
chmod +x node_modules/.bin/vite
chmod +x node_modules/.bin/tsc
chmod +x node_modules/typescript/bin/tsc
npm run build
ls -la dist
systemctl reload nginx

cd /projects/ArxivPaper4/Mobile
npm install
chmod +x node_modules/.bin/vite
chmod +x node_modules/.bin/tsc
chmod +x node_modules/typescript/bin/tsc
npm run build
ls -la dist
systemctl reload nginx

systemctl restart arxiv-api