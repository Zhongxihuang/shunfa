# Alembic 数据库迁移

## 常用命令（在 backend/ 目录下运行）

```bash
# 生成新迁移（修改 models.py 后运行）
alembic revision --autogenerate -m "描述改动"

# 应用所有未执行的迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1

# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```

## 工作流

1. 修改 `app/models.py`
2. `alembic revision --autogenerate -m "add xxx field"`
3. 检查生成的迁移文件是否符合预期
4. `alembic upgrade head`
