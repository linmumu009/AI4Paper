"""
初始化超级管理员账号脚本。
在服务器上首次部署时运行，用于创建第一个 superadmin 用户。
admin 账号初始化跳过手机号短信验证，可通过可选参数绑定手机号。

用法：
    cd Sever
    python init_admin.py <用户名> <密码> [手机号]

示例：
    python init_admin.py admin MyStr0ngP@ss
    python init_admin.py admin MyStr0ngP@ss 13800138000
"""

import sys
import os

# 确保能 import 同目录的 services
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import auth_service


def main():
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("用法: python init_admin.py <用户名> <密码> [手机号]")
        print("示例: python init_admin.py admin MyStr0ngP@ss")
        print("示例: python init_admin.py admin MyStr0ngP@ss 13800138000")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    phone = sys.argv[3] if len(sys.argv) == 4 else None

    # 初始化数据库表
    auth_service.init_auth_db()

    # 检查用户是否已存在
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "paper_analysis.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT id, username, role, tier FROM auth_users WHERE username = ?",
        (username.lower(),)
    ).fetchone()

    if existing:
        # 已存在则直接提权，并可选更新手机号
        updates = "role = 'superadmin', tier = 'pro_plus'"
        params: list = [existing["id"]]
        if phone:
            updates = "role = 'superadmin', tier = 'pro_plus', phone = ?, phone_verified = 1"
            params = [phone] + params
        conn.execute(
            f"UPDATE auth_users SET {updates} WHERE id = ?",
            params,
        )
        conn.commit()
        conn.close()
        print(f"✅ 用户 '{existing['username']}' 已更新为 superadmin + pro_plus")
        if phone:
            print(f"   手机号: {phone}")
    else:
        conn.close()
        # 注册新用户（admin 初始化跳过 SMS 验证，直接传入 phone）
        from fastapi import HTTPException
        try:
            user = auth_service.register_user(username, password, phone=phone)
        except HTTPException as e:
            print(f"❌ 注册失败: {e.detail}")
            sys.exit(1)

        # 提升为 superadmin + pro_plus
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE auth_users SET role = 'superadmin', tier = 'pro_plus' WHERE id = ?",
            (user["id"],)
        )
        conn.commit()
        conn.close()
        print(f"✅ 超级管理员账号创建成功！")
        print(f"   用户名: {username}")
        print(f"   角色:   superadmin")
        print(f"   套餐:   pro_plus（无限额）")
        if phone:
            print(f"   手机号: {phone}")
        print(f"\n现在可以登录并通过 /admin/users 管理其他用户了。")


if __name__ == "__main__":
    main()
