import aiohttp
import json
import re
import time
import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig


@register("temp_email", "victical", "临时邮箱生成插件", "1.0.0", "https://github.com/victical/astrbot_plugin_temp-email")
class TempEmailPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.api_key = config.get("api_key", "idr_f9389715f799f012916dabbdf0b0fa24")
        # 直接在代码中设置默认的API地址和邮箱类型
        self.generate_url = "https://apiok.us/api/cbea/generate/v1"
        self.messages_url = "https://apiok.us/api/cbea/messages/v1"
        self.message_detail_url = "https://apiok.us/api/cbea/message/detail/v1"
        self.email_type = "*"
        # 用于存储用户的邮箱ID，key为用户的unified_msg_origin
        self.user_email_ids = {}
        # 用于存储用户的邮件ID列表，key为用户的unified_msg_origin
        self.user_message_ids = {}

    def _clean_email_content(self, content: str) -> str:
        """清理邮件内容，移除不必要的格式代码"""
        if not content:
            return "无内容"
        
        # 直接截断--- mail_boundary ---后的所有内容
        boundary_index = content.find('--- mail_boundary ---')
        if boundary_index != -1:
            content = content[:boundary_index]
        
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        
        # 解码常见的HTML实体
        content = content.replace('&nbsp;', ' ')
        content = content.replace('&amp;', '&')
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&quot;', '"')
        
        # 清理多余的空白字符
        content = re.sub(r'\s+', ' ', content)
        content = content.strip()
        
        # 如果清理后内容为空，返回提示
        if not content or content.isspace():
            return "邮件内容为空"
        
        return content

    def _timestamp_to_local_time(self, timestamp) -> str:
        """将时间戳转换为本地时间格式"""
        try:
            # 处理不同格式的时间戳
            if isinstance(timestamp, str):
                # 如果是字符串，尝试转换为浮点数
                timestamp = float(timestamp)
            
            # 检查时间戳的位数来判断是秒还是毫秒
            if timestamp > 1e12:  # 毫秒时间戳
                timestamp = timestamp / 1000
            
            # 转成本地时区的时间元组
            local_time = time.localtime(timestamp)
            # 格式化为易读的格式
            formatted_local = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
            return formatted_local
            
        except (ValueError, TypeError):
            # 如果转换失败，返回原始时间戳
            return str(timestamp) if timestamp else "未知时间"

    @filter.command("获取邮箱")
    async def generate_temp_email(self, event: AstrMessageEvent):
        """生成临时邮箱地址"""
        try:
            # 调用临时邮箱API
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=65)) as session:
                # 根据API文档，使用query string传递apikey
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json"
                }
                
                # 根据示例代码，添加type参数
                params = {
                    "apikey": self.api_key,
                    "type": self.email_type
                }
                
                async with session.get(self.generate_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            
                            result = data.get("result", {})
                            
                            # 获取邮箱地址
                            email = None
                            if isinstance(result, dict):
                                email = result.get("email") or result.get("mail") or result.get("address")
                            elif isinstance(result, str):
                                email = result
                            
                            if email:
                                email_id = result.get("id", "") if isinstance(result, dict) else ""
                                
                                if email_id:
                                    user_origin = event.unified_msg_origin
                                    self.user_email_ids[user_origin] = {
                                        "email_id": email_id,
                                        "email_address": email,
                                        "created_time": __import__('time').time()
                                    }
                                
                                reply_text = f"✅ 临时邮箱生成成功！\n\n📧 邮箱地址：{email}"
                                if email_id:
                                    reply_text += f"\n🆔 邮箱ID：{email_id}"
                                reply_text += f"\n\n⚠️ 注意：此邮箱为临时邮箱，请及时使用。"
                                reply_text += f"\n📬 使用 邮箱列表 快速查看邮件列表"
                                yield event.plain_result(reply_text)
                            else:
                                yield event.plain_result("❌ 生成邮箱失败，请稍后重试")
                                
                        except json.JSONDecodeError:
                            yield event.plain_result("❌ API返回的JSON格式无效")
                    else:
                        yield event.plain_result("❌ 网络请求失败")
                        
        except Exception:
            yield event.plain_result("❌ 生成临时邮箱时发生错误")

    @filter.command("邮箱列表")
    async def get_email_messages(self, event: AstrMessageEvent):
        """获取指定邮箱的邮件列表"""
        # 从消息中解析邮箱ID参数
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        email_id = None
        if len(parts) > 1:
            # 如果有参数，使用参数作为邮箱ID
            email_id = parts[1].strip()
        
        if not email_id:
            # 如果没有参数，尝试使用用户存储的邮箱ID
            user_origin = event.unified_msg_origin
            if user_origin in self.user_email_ids:
                email_id = self.user_email_ids[user_origin]["email_id"]
            else:
                yield event.plain_result("❌ 未找到您的邮箱信息，请先使用 获取邮箱 生成邮箱，或手动指定邮箱ID\n\n使用方法: 邮箱列表 <邮箱ID>")
                return
        try:
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=65)) as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json"
                }
                
                params = {
                    "apikey": self.api_key,
                    "id": email_id
                }
                
                async with session.get(self.messages_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        try:
                            response_text = await response.text()
                            
                            data = json.loads(response_text)
                            result = data.get("result", [])
                            
                            messages = []
                            if isinstance(result, dict) and "messages" in result:
                                messages = result["messages"]
                            elif isinstance(result, list):
                                messages = result
                            
                            if messages and len(messages) > 0:
                                # 缓存用户的邮件ID列表
                                user_origin = event.unified_msg_origin
                                message_ids = [msg.get("id", "") for msg in messages if msg.get("id")]
                                self.user_message_ids[user_origin] = message_ids
                                
                                reply_text = f"📬 邮件列表 (邮箱ID: {email_id})\n\n"
                                display_messages = messages[:10] if len(messages) > 10 else messages
                                
                                for i, message in enumerate(display_messages, 1):
                                    sender = message.get("from", "未知发件人")
                                    subject = message.get("subject", "无主题")
                                    msg_id = message.get("id", "")
                                    msg_time = message.get("time", message.get("date", ""))
                                    # 转换时间戳为本地时间
                                    local_time = self._timestamp_to_local_time(msg_time)
                                    reply_text += f"{i}. 📧 标题：{subject}\n"
                                    reply_text += f"   👤 发件人: {sender}\n"
                                    reply_text += f"   📅 时间: {local_time}\n"
                                    reply_text += "\n"
                                
                                if len(messages) > 10:
                                    reply_text += f"... 还有 {len(messages) - 10} 封邮件未显示\n\n"
                                
                                reply_text += "💡 提示: 直接输入 查看正文 即可查看最新邮件内容"
                            else:
                                reply_text = f"📭 暂无邮件\n\n该邮箱(ID: {email_id})\n目前没有收到任何邮件。"
                            
                            yield event.plain_result(reply_text)
                                
                        except json.JSONDecodeError as e:
                            yield event.plain_result(f"❌ 邮件列表API返回的JSON格式无效: {e}")
                    else:
                        response_text = await response.text()
                        yield event.plain_result(f"❌ 网络请求失败，状态码: {response.status}")
                        
        except Exception as e:
            yield event.plain_result(f"❌ 获取邮件列表时发生错误: {e}")

    @filter.command("查看正文")
    async def get_message_detail(self, event: AstrMessageEvent):
        """获取邮件详情"""
        # 从消息中解析邮件ID参数
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        message_id = None
        if len(parts) >= 2:
            # 如果用户提供了邮件ID，使用用户提供的ID
            message_id = parts[1].strip()
        else:
            # 如果用户没有提供邮件ID，自动使用最新的邮件ID
            user_origin = event.unified_msg_origin
            if user_origin in self.user_message_ids and self.user_message_ids[user_origin]:
                message_id = self.user_message_ids[user_origin][0]  # 使用第一个（最新的）邮件ID
            else:
                yield event.plain_result("❌ 未找到邮件ID，请先使用 邮箱列表 查看邮件，或手动指定邮件ID\n\n使用方法: 查看正文 <邮件ID>")
                return
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=65)) as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json"
                }
                
                params = {
                    "apikey": self.api_key,
                    "id": message_id
                }
                
                async with session.get(self.message_detail_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        try:
                            response_text = await response.text()
                            
                            data = json.loads(response_text)
                            result = data.get("result", {})
                            
                            if result:
                                # 确保result是字典类型
                                if not isinstance(result, dict):
                                    yield event.plain_result(f"❌ 邮件详情格式错误")
                                    return
                                
                                sender = result.get("from", "未知发件人")
                                subject = result.get("subject", "无主题")
                                content = result.get("content", "无内容")
                                
                                cleaned_content = self._clean_email_content(content)
                                
                                reply_text = f"📧 邮件详情 (ID: {message_id})\n\n"
                                reply_text += f"📋 主题: {subject}\n"
                                reply_text += f"👤 发件人: {sender}\n"
                                reply_text += f"📄 内容:{cleaned_content}"
                                
                                if len(reply_text) > 2000:
                                    reply_text = reply_text[:1900] + "\n... (内容过长，已截断)"
                                
                                yield event.plain_result(reply_text)
                            else:
                                yield event.plain_result(f"❌ 获取邮件详情失败，请检查邮件ID: {message_id}")
                                
                        except json.JSONDecodeError as e:
                            yield event.plain_result(f"❌ 邮件详情API返回的JSON格式无效: {e}")
                    else:
                        response_text = await response.text()
                        yield event.plain_result(f"❌ 网络请求失败，状态码: {response.status}")
                        
        except Exception as e:
            yield event.plain_result(f"❌ 获取邮件详情时发生错误: {e}")

    


    @filter.command("邮箱帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示插件帮助信息"""
        help_text = """📧 临时邮箱插件帮助

🔸 获取邮箱 - 生成一个临时邮箱地址
🔸 邮箱列表 - 查看当前邮箱的邮件列表
🔸 查看正文 - 自动查看最新邮件内容（无需输入邮件ID）
🔸 查看正文 <邮件ID> - 查看指定邮件详情
🔸 邮箱帮助 - 显示此帮助信息

📝 简化使用流程：
1. 使用 获取邮箱 生成临时邮箱
2. 复制邮箱地址用于注册或接收邮件
3. 使用 邮箱列表 快速查看邮件
4. 直接输入 查看正文 即可查看最新邮件内容

💡 如有问题，请联系管理员检查API配置"""
        
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件卸载时调用"""
        self.user_email_ids.clear()
        self.user_message_ids.clear()