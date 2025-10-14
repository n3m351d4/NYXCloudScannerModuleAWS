# 🗑️ NYX Cloud Scanner Module AWS - Log Deletion Techniques

## 📊 Статистика реализации:
- **12 техник эскалации** (10 критических + 1 высокая + 1 средняя)
- **67 операций проверки** включая CloudWatch/CloudTrail операции
- **60 баллов** максимальная оценка критичности

## 🔴 Критические техники сокрытия следов атак

### **CloudTrail Log Deletion (60 баллов)**
```python
'cloudtrail_delete_trail': 60,  # Удаление CloudTrail трейлов - максимальная угроза для сокрытия аудита
'cloudtrail_stop_logging': 55,  # Остановка логирования CloudTrail
'cloudtrail_put_event_selectors': 50,  # Изменение селекторов событий для фильтрации логов
```

**Что можно сделать:**
- `delete_trail()` - полное удаление трейлов аудита
- `stop_logging()` - остановка логирования без удаления трейла
- `put_event_selectors()` - фильтрация событий для сокрытия активности

### **CloudWatch Logs Deletion (50 баллов)**
```python
'cloudwatch_logs_delete_log_group': 50,  # Удаление групп логов CloudWatch
'cloudwatch_logs_stop_logging': 45,  # Остановка логирования CloudWatch Logs
'cloudwatch_logs_put_retention_policy': 40,  # Изменение политики хранения логов
'cloudwatch_logs_delete_log_stream': 35,  # Удаление потоков логов
```

**Что можно сделать:**
- `delete_log_group()` - удаление групп логов приложений
- `stop_logging()` - остановка логирования Lambda функций
- `put_retention_policy()` - сокращение времени хранения логов до 1 дня
- `delete_log_stream()` - удаление конкретных потоков логов

### **Forensic Cleanup (40 баллов)**
```python
'secrets_manager_delete_secret': 40,  # Удаление секретов для сокрытия следов атаки
's3_delete_bucket': 35,  # Удаление S3 бакетов для сокрытия следов атаки
'lambda_delete_function': 35,  # Удаление Lambda функций для сокрытия следов атаки
```

## 🎯 Новые флоу атак

### **Log Deletion Attack**
- **Требуемые сервисы:** `cloudtrail_delete_trail`, `cloudtrail_stop_logging`, `cloudwatch_logs_delete_log_group`
- **Роли:** `CloudTrailFullAccess`, `CloudWatchLogsFullAccess`
- **Описание:** Удаление логов и сокрытие следов атак

### **Forensic Cleanup Attack**
- **Требуемые сервисы:** `secrets_manager_delete_secret`, `s3_delete_bucket`, `lambda_delete_function`
- **Роли:** `SecretsManagerFullAccess`, `S3FullAccess`, `AWSLambdaFullAccess`
- **Описание:** Удаление следов атаки и очистка инфраструктуры

## 🚨 Эксплуатационная ценность

### **Максимальная угроза (60 баллов):**
- **CloudTrail Delete Trail** - полное сокрытие аудита
- Полная невидимость для SOC/SIEM систем
- Невозможность расследования инцидентов

### **Высокая угроза (50-55 баллов):**
- **CloudTrail Stop Logging** - остановка аудита
- **CloudWatch Logs Delete Group** - удаление логов приложений
- Частичное сокрытие следов атак

### **Средняя угроза (40-45 баллов):**
- **Forensic Cleanup** - удаление артефактов атак
- **CloudWatch Logs Stop Logging** - остановка логирования функций
- Очистка инфраструктуры от следов

## 🔥 Реальные сценарии атак

### **Сценарий 1: Полное сокрытие аудита**
```bash
# 1. Удаление CloudTrail трейлов
aws cloudtrail delete-trail --name production-trail

# 2. Остановка логирования
aws cloudtrail stop-logging --name backup-trail

# 3. Удаление групп логов
aws logs delete-log-group --log-group-name /aws/lambda/monitoring-function
```

### **Сценарий 2: Фильтрация событий**
```bash
# Изменение селекторов для сокрытия активности
aws cloudtrail put-event-selectors \
    --trail-name production-trail \
    --event-selectors '[{
        "ReadWriteType": "ReadOnly",
        "IncludeManagementEvents": false,
        "DataResources": [{
            "Type": "AWS::S3::Object",
            "Values": ["arn:aws:s3:::malicious-bucket/*"]
        }]
    }]'
```

### **Сценарий 3: Сокращение времени хранения**
```bash
# Установка минимального времени хранения
aws logs put-retention-policy \
    --log-group-name /aws/lambda/security-monitor \
    --retention-in-days 1
```

## ⚠️ Критические последствия

1. **Полная потеря аудита** - невозможность расследования
2. **Сокрытие APT атак** - долгосрочное присутствие
3. **Нарушение compliance** - GDPR, SOX, PCI-DSS
4. **Блокировка расследований** - отсутствие доказательств
5. **Повторные атаки** - невозможность обнаружения

