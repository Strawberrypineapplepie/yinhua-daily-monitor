#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
银华日利套利监控器
功能: 每10分钟检测银华日利(511880)折溢价，多策略分析，飞书推送
"""

import os
import sys
import io

# 修复Windows控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import sys
import json
import time
import argparse
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import schedule

# ============== 配置区 ==============
FUND_CODE = "511880"  # 银华日利场内代码
FUND_NAME = "银华日利"

# 收益参数 (基于文档)
DAILY_RETURN_MIN = 0.003  # 万0.3
DAILY_RETURN_MAX = 0.004  # 万0.4
DAILY_RETURN_AVG = 0.0035  # 万0.35 (速算值)

# 策略阈值 (基于文档)
DISCOUNT_THRESHOLD = 0.0008  # 折价万0.8 触发模式A
PREMIUM_THRESHOLD = 0.0015  # 溢价万1.5 触发模式B
T_MODE_THRESHOLD = 0.0005   # 溢价万0.5 触发模式C
TUESDAY_THRESHOLD = 0.001   # 周二溢价万1 触发模式D

# 数据源
MX_APIKEY = os.environ.get("MX_APIKEY", "").strip()

# 飞书开放平台配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a92fee8f66791cd1").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "69X0AJdYp8ZBNRIdWMv7Oe4PJGY4WUNX").strip()
FEISHU_RECEIVE_ID = os.environ.get("FEISHU_RECEIVE_ID", "ou_9457a90140c97c4d7ff683801686ba56").strip()  # 接收消息的用户open_id
FEISHU_RECEIVE_TYPE = os.environ.get("FEISHU_RECEIVE_TYPE", "open_id").strip()  # open_id, user_id, union_id, chat_id

# 备用数据源URL
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_FUND_URL = "https://fund.eastmoney.com/pingzhongdata/511880.html"
TENCENT_QUOTE_URL = "https://web.sqt.gtimg.cn/q="  # 腾讯股票接口


class YinhuaMonitor:
    """银华日利监控核心类"""
    
    def __init__(self):
        self.last_nav = None  # 昨日净值
        self.current_price = None  # 当前场内价格
        self.iopv = None  # IOPV实时净值
        self.today_date = datetime.now().strftime("%Y-%m-%d")
        
    def get_quote_data(self) -> Dict[str, Any]:
        """获取银华日利实时行情数据"""
        data = {
            "price": None,
            "iopv": None,
            "change": None,
            "volume": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 方法1: 使用东方财富妙想API
        if MX_APIKEY:
            try:
                result = self._fetch_from_mx()
                if result and result.get("price"):
                    data.update(result)
                    print(f"✅ 从妙想API获取数据成功: 价格={result.get('price')}")
                    return data
                else:
                    print(f"⚠️ 妙想API返回数据无效")
            except Exception as e:
                print(f"⚠️ 妙想API获取失败: {e}")
        
        # 方法2: 使用东方财富备用接口
        try:
            result = self._fetch_from_eastmoney()
            if result:
                data.update(result)
                print(f"✅ 从东方财富备用接口获取数据成功")
                return data
        except Exception as e:
            print(f"⚠️ 东方财富备用接口获取失败: {e}")
        
        # 方法3: 使用腾讯股票接口 (第三备用)
        try:
            result = self._fetch_from_tencent()
            if result:
                data.update(result)
                print(f"✅ 从腾讯接口获取数据成功")
                return data
        except Exception as e:
            print(f"⚠️ 腾讯接口获取失败: {e}")
        
        return data
    
    def _fetch_from_mx(self) -> Optional[Dict[str, Any]]:
        """从东方财富妙想API获取数据"""
        url = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"
        headers = {
            "Content-Type": "application/json",
            "apikey": MX_APIKEY
        }
        payload = {
            "toolQuery": f"银华日利{FUND_CODE}最新价格行情"
        }
        
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, json=payload)
            result = resp.json()
            
            # 解析新的API返回格式
            # result["data"]["data"]["searchDataResultDTO"]["dataTableDTOList"][0]["table"]["f2"]
            if result.get("status") == 0 or result.get("code") == 0:
                try:
                    data_inner = result.get("data", {})
                    if "data" in data_inner:
                        search_result = data_inner["data"].get("searchDataResultDTO", {})
                    else:
                        search_result = data_inner.get("searchDataResultDTO", {})
                    
                    data_list = search_result.get("dataTableDTOList", [])
                    if data_list:
                        table = data_list[0].get("table", {})
                        name_map = data_list[0].get("nameMap", {})
                        
                        # 提取最新价 (f2)
                        price = None
                        if "f2" in table and table["f2"]:
                            price = float(table["f2"][0])
                        
                        # 如果没有价格，尝试其他字段
                        if not price:
                            for key, values in table.items():
                                if values and key != "headName":
                                    try:
                                        price = float(values[0])
                                        break
                                    except:
                                        continue
                        
                        if price:
                            return {
                                "price": price,
                                "iopv": price,  # 暂用价格代替，后续可单独获取
                                "change": 0,
                                "volume": 0
                            }
                except Exception as e:
                    print(f"解析妙想数据失败: {e}")
        return None
    
    def _fetch_from_eastmoney(self) -> Optional[Dict[str, Any]]:
        """从东方财富备用接口获取数据"""
        params = {
            "secid": f"1.{FUND_CODE}",  # 上海市场
            "fields": "f43,f44,f45,f46,f47,f48,f60,f170,f171"
        }
        
        with httpx.Client(timeout=10, verify=False) as client:
            resp = client.get(EASTMONEY_QUOTE_URL, params=params, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                "Referer": "https://quote.eastmoney.com/"
            })
            result = resp.json()
            
            if result.get("data"):
                d = result["data"]
                # f43: 最新价, f60: IOPV
                price = d.get("f43", 0) / 100 if d.get("f43") else None
                iopv = d.get("f60", 0) / 100 if d.get("f60") else None
                change = d.get("f170", 0) / 100 if d.get("f170") else None
                
                return {
                    "price": price,
                    "iopv": iopv,
                    "change": change
                }
        return None
    
    def _fetch_from_tencent(self) -> Optional[Dict[str, Any]]:
        """从腾讯股票接口获取数据 (第三备用)"""
        url = f"{TENCENT_QUOTE_URL}sh{FUND_CODE}"
        
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            })
            text = resp.text
            
            # 解析腾讯返回格式: v_sh511880="1~银华日利~511880~100.28~昨收~..."
            if "~" in text:
                parts = text.split("~")
                if len(parts) >= 4:
                    try:
                        price = float(parts[3])
                        if price > 0:
                            return {
                                "price": price,
                                "iopv": None,  # 腾讯无IOPV
                                "change": None
                            }
                    except (ValueError, IndexError):
                        pass
        return None
    
    def get_last_nav(self) -> Optional[float]:
        """获取上一交易日净值"""
        # 方法1: 从妙想API获取
        if MX_APIKEY:
            try:
                url = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"
                headers = {
                    "Content-Type": "application/json",
                    "apikey": MX_APIKEY
                }
                payload = {
                    "toolQuery": f"银华日利{FUND_CODE}昨日净值"
                }
                
                with httpx.Client(timeout=10) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    result = resp.json()
                    
                    if result.get("code") == 0:
                        data_list = result.get("data", {}).get("dataTableDTOList", [])
                        if data_list:
                            rows = data_list[0].get("dataTableDTO", {}).get("tableBody", [])
                            if rows:
                                nav = float(rows[0].get("单位净值", rows[0].get("净值", 0)))
                                return nav
            except Exception as e:
                print(f"⚠️ 获取昨日净值失败: {e}")
        
        # 方法2: 从天天基金网获取
        try:
            url = f"http://fundgz.1234567.com.cn/js/{FUND_CODE}.js"
            with httpx.Client(timeout=10) as client:
                resp = client.get(url)
                text = resp.text
                # 解析JSONP格式
                if text.startswith("jsonpgz"):
                    json_str = text[8:-2]  # 去掉 jsonpgz( 和 );
                    data = json.loads(json_str)
                    return float(data.get("dwjz", 0))
        except Exception as e:
            print(f"⚠️ 天天基金获取净值失败: {e}")
        
        return None
    
    def get_holiday_days(self) -> int:
        """获取当前是否节假日及放假天数 (简化版，实际可接入节假日API)"""
        # 这里可以接入节假日API或手动配置
        # 清明: 4月4-6日
        # 劳动节: 5月1-5日
        # 端午: 农历五月初五
        # 中秋: 农历八月十五
        # 国庆: 10月1-7日
        
        today = datetime.now()
        
        # 简化判断: 检查是否有连续的非交易日
        # 实际使用时建议接入专业节假日API
        return 0
    
    def calculate_real_value(self, last_nav: float) -> Dict[str, float]:
        """计算银华日利实际价值 (基于文档公式)"""
        today = datetime.now()
        weekday = today.weekday()  # 0=周一, 4=周五
        
        # 计算收益天数
        holiday_days = self.get_holiday_days()
        
        if holiday_days > 0:
            # 公式3: 节假日
            yield_days = holiday_days + 1
            formula = "节假日公式"
        elif weekday == 4:  # 周五
            # 公式2: 周五晚上(含周末)
            yield_days = 3
            formula = "周五公式"
        else:
            # 公式1: 正常工作日
            yield_days = 1
            formula = "正常工作日公式"
        
        # 计算实际价值范围
        real_value_min = last_nav + DAILY_RETURN_MIN * yield_days
        real_value_max = last_nav + DAILY_RETURN_MAX * yield_days
        real_value_avg = last_nav + DAILY_RETURN_AVG * yield_days
        
        return {
            "min": real_value_min,
            "max": real_value_max,
            "avg": real_value_avg,
            "yield_days": yield_days,
            "formula": formula
        }
    
    def analyze_premium_discount(self, price: float, real_value: float) -> Dict[str, Any]:
        """分析折溢价情况"""
        diff = real_value - price
        diff_pct = diff / price
        
        # 判断类型
        if diff > 0:
            status = "折价"
            abs_diff_pct = abs(diff_pct)
        elif diff < 0:
            status = "溢价"
            abs_diff_pct = abs(diff_pct)
        else:
            status = "平价"
            abs_diff_pct = 0
        
        # 计算年化收益
        annualized_return = abs_diff_pct * 365 * 100  # 百分比
        
        return {
            "status": status,
            "diff": diff,
            "diff_pct": diff_pct,
            "abs_diff_pct": abs_diff_pct,
            "diff_wan": abs_diff_pct * 10000,  # 万分比
            "annualized_return": annualized_return
        }
    
    def get_strategy_recommendation(self, analysis: Dict, weekday: int) -> List[Dict]:
        """根据折溢价情况生成策略建议"""
        recommendations = []
        status = analysis["status"]
        diff_wan = analysis["diff_wan"]
        
        # 模式A: 折价买入赎回套利
        if status == "折价" and diff_wan >= 0.8:
            recommendations.append({
                "mode": "A",
                "name": "折价买入赎回套利",
                "risk": "几乎无风险",
                "trigger": f"折价万{diff_wan:.2f} ≥ 万0.8",
                "action": "建议立即场内买入，收盘前赎回",
                "expected_return": f"预计收益: 万{diff_wan:.2f}",
                "tips": "推荐使用某银某河券商(T+1盘中到账)"
            })
        elif status == "折价" and diff_wan >= 0.3:
            recommendations.append({
                "mode": "A",
                "name": "折价买入赎回套利(关注)",
                "risk": "几乎无风险",
                "trigger": f"折价万{diff_wan:.2f} (接近触发)",
                "action": "建议关注，若折价扩大至万0.8可操作",
                "expected_return": f"预计收益: 万{diff_wan:.2f}",
                "tips": "当前可小仓位试水"
            })
        
        # 模式B: 溢价申购卖出套利
        if status == "溢价" and diff_wan >= 1.5:
            recommendations.append({
                "mode": "B",
                "name": "溢价申购卖出套利",
                "risk": "中低风险",
                "trigger": f"溢价万{diff_wan:.2f} ≥ 万1.5",
                "action": "尾盘申购，T+2到账后卖出",
                "expected_return": f"预计收益: 万{diff_wan:.2f} (扣除T+2波动风险)",
                "tips": "注意: 承担T+2价格波动风险"
            })
        
        # 模式C: 日内做T
        if status == "溢价" and diff_wan <= 0.5:
            recommendations.append({
                "mode": "C",
                "name": "日内做T",
                "risk": "低风险",
                "trigger": f"溢价万{diff_wan:.2f} ≤ 万0.5",
                "action": "可尝试低价买入，高价卖出",
                "expected_return": "收益取决于日内波动",
                "tips": "结合IOPV判断买卖时机"
            })
        
        # 模式D: 周二特殊策略
        if weekday == 1 and status == "溢价" and diff_wan >= 1.0:  # 周二
            recommendations.append({
                "mode": "D",
                "name": "周二特殊策略",
                "risk": "中低风险",
                "trigger": f"周二溢价万{diff_wan:.2f} ≥ 万1",
                "action": "周二溢价申购 → 周四卖出 + 逆回购",
                "expected_return": f"预计收益: 万{diff_wan:.2f} + 逆回购收益",
                "tips": "优势: 避免周末风险"
            })
        
        # 无明显机会
        if not recommendations:
            if status == "折价":
                recommendations.append({
                    "mode": "观望",
                    "name": "轻微折价观望",
                    "risk": "-",
                    "trigger": f"折价万{diff_wan:.2f} < 万0.8",
                    "action": "继续关注，等待更好的买入机会",
                    "expected_return": "-",
                    "tips": "折价幅度不足，不建议操作"
                })
            else:
                recommendations.append({
                    "mode": "观望",
                    "name": "轻微溢价观望",
                    "risk": "-",
                    "trigger": f"溢价万{diff_wan:.2f}",
                    "action": "继续关注",
                    "expected_return": "-",
                    "tips": "溢价幅度不够大，风险收益比不佳"
                })
        
        return recommendations
    
    def get_feishu_token(self) -> Optional[str]:
        """获取飞书 tenant_access_token"""
        if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
            print("⚠️ 未配置飞书 APP_ID 或 APP_SECRET")
            return None
        
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {
                "app_id": FEISHU_APP_ID,
                "app_secret": FEISHU_APP_SECRET
            }
            
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                result = resp.json()
                
                if result.get("code") == 0:
                    return result.get("tenant_access_token")
                else:
                    print(f"❌ 获取飞书token失败: {result}")
                    return None
        except Exception as e:
            print(f"❌ 获取飞书token异常: {e}")
            return None
    
    def send_feishu(self, message: Dict) -> bool:
        """发送飞书消息 (使用开放平台API)"""
        if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
            print("⚠️ 未配置飞书凭证，跳过推送")
            return False
        
        # 1. 获取 access token
        token = self.get_feishu_token()
        if not token:
            print("⚠️ 无法获取飞书token，跳过推送")
            return False
        
        # 2. 构建消息卡片
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": message["title"]
                },
                "template": message.get("color", "blue")
            },
            "elements": message["elements"]
        }
        
        # 3. 发送消息
        try:
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            params = {
                "receive_id_type": FEISHU_RECEIVE_TYPE
            }
            payload = {
                "receive_id": FEISHU_RECEIVE_ID,
                "msg_type": "interactive",
                "content": json.dumps(card)
            }
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, params=params, json=payload, headers=headers)
                result = resp.json()
                
                if result.get("code") == 0:
                    print("✅ 飞书推送成功")
                    return True
                else:
                    print(f"❌ 飞书推送失败: {result}")
                    return False
        except Exception as e:
            print(f"❌ 飞书推送异常: {e}")
            return False
    
    def run_once(self, send_notification: bool = True) -> Dict[str, Any]:
        """执行一次监控检测"""
        now = datetime.now()
        weekday = now.weekday()
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        
        print(f"\n{'='*50}")
        print(f"📊 银华日利监控 [{now.strftime('%Y-%m-%d %H:%M:%S')} {weekday_names[weekday]}]")
        print(f"{'='*50}\n")
        
        # 1. 获取实时行情
        print("📡 正在获取实时行情...")
        quote_data = self.get_quote_data()
        
        if not quote_data.get("price"):
            return {"error": "无法获取实时行情数据"}
        
        price = quote_data["price"]
        iopv = quote_data.get("iopv", price)
        
        # 2. 获取昨日净值
        print("📡 正在获取昨日净值...")
        last_nav = self.get_last_nav()
        
        if not last_nav:
            # 使用IOPV估算
            last_nav = iopv - DAILY_RETURN_AVG
            print(f"⚠️ 无法获取昨日净值，使用IOPV估算: {last_nav:.4f}")
        
        # 3. 计算实际价值
        real_value = self.calculate_real_value(last_nav)
        
        # 4. 分析折溢价
        analysis = self.analyze_premium_discount(price, real_value["avg"])
        
        # 5. 生成策略建议
        recommendations = self.get_strategy_recommendation(analysis, weekday)
        
        # 6. 构建报告
        report = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "weekday": weekday_names[weekday],
            "quote": {
                "price": price,
                "iopv": iopv,
                "last_nav": last_nav,
                "real_value_min": real_value["min"],
                "real_value_max": real_value["max"],
                "real_value_avg": real_value["avg"],
                "yield_days": real_value["yield_days"],
                "formula": real_value["formula"]
            },
            "analysis": analysis,
            "recommendations": recommendations
        }
        
        # 7. 打印报告
        self._print_report(report)
        
        # 8. 发送飞书
        if send_notification:
            feishu_msg = self._build_feishu_message(report)
            self.send_feishu(feishu_msg)
        
        return report
    
    def _print_report(self, report: Dict):
        """打印监控报告"""
        q = report["quote"]
        a = report["analysis"]
        r = report["recommendations"]
        
        print("\n📈 当前状态:")
        print(f"  - 场内价格: {q['price']:.4f}")
        print(f"  - IOPV净值: {q['iopv']:.4f}" if q['iopv'] else "  - IOPV净值: N/A")
        print(f"  - 昨日净值: {q['last_nav']:.4f}")
        print(f"  - 预估净值: {q['real_value_avg']:.4f} (范围: {q['real_value_min']:.4f} - {q['real_value_max']:.4f})")
        print(f"  - 计算公式: {q['formula']} (收益天数: {q['yield_days']})")
        
        print(f"\n💰 折溢价分析:")
        print(f"  - 状态: {a['status']}")
        print(f"  - 幅度: 万{a['diff_wan']:.2f}")
        print(f"  - 年化收益: {a['annualized_return']:.2f}%")
        
        print(f"\n🎯 策略建议:")
        for rec in r:
            print(f"  [{rec['mode']}] {rec['name']}")
            print(f"    触发条件: {rec['trigger']}")
            print(f"    操作建议: {rec['action']}")
            print(f"    预期收益: {rec['expected_return']}")
            print(f"    提示: {rec['tips']}")
        
        print("\n" + "="*50)
    
    def _build_feishu_message(self, report: Dict) -> Dict:
        """构建飞书消息卡片"""
        q = report["quote"]
        a = report["analysis"]
        r = report["recommendations"]
        
        # 确定颜色
        if a["status"] == "折价" and a["diff_wan"] >= 0.8:
            color = "green"  # 机会好
        elif a["status"] == "溢价" and a["diff_wan"] >= 1.5:
            color = "orange"  # 有机会但有风险
        else:
            color = "blue"  # 正常
        
        # 构建元素
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📈 当前状态**\n"
                              f"场内价格: **{q['price']:.4f}**\n"
                              f"IOPV净值: **{q['iopv']:.4f}**\n"
                              f"昨日净值: **{q['last_nav']:.4f}**\n"
                              f"预估净值: **{q['real_value_avg']:.4f}**\n"
                              f"计算公式: {q['formula']} (收益天数: {q['yield_days']})"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**💰 折溢价分析**\n"
                              f"状态: **{a['status']}**\n"
                              f"幅度: **万{a['diff_wan']:.2f}**\n"
                              f"年化收益: **{a['annualized_return']:.2f}%**"
                }
            },
            {"tag": "hr"}
        ]
        
        # 添加策略建议
        for rec in r:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**🎯 [{rec['mode']}] {rec['name']}**\n"
                              f"触发条件: {rec['trigger']}\n"
                              f"操作建议: {rec['action']}\n"
                              f"预期收益: {rec['expected_return']}\n"
                              f"提示: {rec['tips']}"
                }
            })
        
        return {
            "title": f"📊 银华日利监控 [{report['timestamp']}]",
            "color": color,
            "elements": elements
        }


def is_trading_time() -> bool:
    """判断是否在交易时间"""
    now = datetime.now()
    weekday = now.weekday()
    
    # 周末不交易
    if weekday >= 5:
        return False
    
    hour = now.hour
    minute = now.minute
    
    # 上午: 9:30 - 11:30
    if 9 <= hour < 12:
        if hour == 9 and minute < 30:
            return False
        if hour == 11 and minute > 30:
            return False
        return True
    
    # 下午: 13:00 - 15:00
    if 13 <= hour < 15:
        return True
    if hour == 15 and minute == 0:
        return True
    
    return False


def main():
    parser = argparse.ArgumentParser(description="银华日利套利监控器")
    parser.add_argument("--once", action="store_true", help="执行一次检测后退出")
    parser.add_argument("--schedule", action="store_true", help="启动定时监控")
    parser.add_argument("--fetch-only", action="store_true", help="仅获取数据不推送")
    parser.add_argument("--test", action="store_true", help="测试模式(使用模拟数据)")
    args = parser.parse_args()
    
    monitor = YinhuaMonitor()
    
    if args.test:
        # 测试模式
        print("🧪 测试模式")
        # 模拟数据
        monitor.last_nav = 100.3762
        monitor.current_price = 100.3820
        monitor.iopv = 100.3850
        report = monitor.run_once(send_notification=False)
        print("\n✅ 测试完成")
        return
    
    if args.fetch_only:
        # 仅获取数据
        report = monitor.run_once(send_notification=False)
        print("\n✅ 数据获取完成")
        return
    
    if args.once:
        # 执行一次
        report = monitor.run_once(send_notification=True)
        if "error" in report:
            print(f"\n❌ 检测失败: {report['error']}")
            sys.exit(1)
        print("\n✅ 检测完成")
        return
    
    if args.schedule:
        # 定时监控
        print("🕐 启动定时监控 (开市时间每10分钟检测)")
        print("按 Ctrl+C 停止\n")
        
        def job():
            if is_trading_time():
                monitor.run_once(send_notification=True)
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{now}] 非交易时间，跳过检测")
        
        # 每10分钟执行
        schedule.every(10).minutes.do(job)
        
        # 立即执行一次
        job()
        
        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == "__main__":
    main()
