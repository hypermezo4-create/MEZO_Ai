# mezo-control-plane

لوحة التحكم والسيطرة لمنصة MEZO AI تحتوي على وكلاء النظام (System, Deployment, Monitoring, Security)، مدير المهام، محرك سير العمل، وتطبيقات الربط مع Fly.io و GitHub و Docker.

## التشغيل المحلي
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```
