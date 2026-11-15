"""演示数据。本地起服务后必须有用户，否则 X-User-Id / Bearer 都过不了鉴权。

三个用户是刻意设计的对照：
- alice：普通员工，只能看 employee 文档
- hr:    HR，能看 employee + hr 文档（越权测试集要用它来验证"能看到"）
- bob:   另一个租户，用来验证 tenant_id 隔离（问同样的问题应该什么都召回不到）

生产环境请换成真 OIDC 后的用户同步，这个文件不参与。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User

# 与 sample_docs/ 下的 ACL 标签配套：employee 为公开制度，hr 为薪酬机密。
DEMO_USERS = [
    {
        "id": "u-alice",
        "email": "alice@acme.com",
        "display_name": "Alice（普通员工）",
        "tenant_id": "acme",
        "roles": ["employee"],
    },
    {
        "id": "u-hr",
        "email": "hr@acme.com",
        "display_name": "HR（人力）",
        "tenant_id": "acme",
        "roles": ["employee", "hr"],
    },
    {
        "id": "u-bob",
        "email": "bob@globex.com",
        "display_name": "Bob（另一租户）",
        "tenant_id": "globex",
        "roles": ["employee"],
    },
]


def seed_demo_users(db: Session) -> int:
    """幂等：已存在（按 id 或 email）就跳过，返回新插入条数。

    两个集合都查一次，是为了避免 id 相同但 email 被占用（或反过来）时
    触发唯一约束报错；幂等性让 `init_db()` 可以在每次重启时安全调用。
    """
    existing = {
        row[0]
        for row in db.query(User.id).filter(User.id.in_([u["id"] for u in DEMO_USERS])).all()
    }
    existing_emails = {
        row[0]
        for row in db.query(User.email)
        .filter(User.email.in_([u["email"] for u in DEMO_USERS]))
        .all()
    }

    added = 0
    for u in DEMO_USERS:
        if u["id"] in existing or u["email"] in existing_emails:
            continue
        db.add(User(**u))
        added += 1

    # 一次性提交，减少启动时的往返；没有新增就不写库。
    if added:
        db.commit()
        print(f"[seed] 写入 {added} 个演示用户：" + "、".join(u["id"] for u in DEMO_USERS))
    return added


if __name__ == "__main__":
    # 允许单独执行 `python -m app.seed` 手动补数据。
    from app.db import SessionLocal

    with SessionLocal() as db:
        n = seed_demo_users(db)
    print("done" if n else "演示用户已存在，无需重复写入")
