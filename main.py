import datetime as dt
import os

from PyQt5 import uic
from PyQt5.QtCore import QSettings, QTime
from qfluentwidgets import (
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    SpinBox,
    TimePicker,
)

from .ClassWidgets.base import PluginBase, SettingsBase  # 导入CW的基类


class Plugin(PluginBase):  # 插件类
    def __init__(self, cw_contexts, method):  # 初始化
        super().__init__(cw_contexts, method)  # 调用父类初始化方法
        self.cw_contexts = cw_contexts
        self.settings = QSettings(f"{self.PATH}/config.ini", QSettings.IniFormat)
        # 初始化设置
        if not self.settings.contains("enable_tip"):
            self.settings.setValue("enable_tip", True)
        if not self.settings.contains("course_count"):
            self.settings.setValue("course_count", 4)
        if not self.settings.contains("tip_time"):
            self.settings.setValue("tip_time", "18:00:00")
        if not self.settings.contains("excluded_courses"):
            self.settings.setValue("excluded_courses", "")
        if not self.settings.contains("notification_duration"):
            self.settings.setValue("notification_duration", 10000)

    def execute(self):  # 自启动执行部分
        # log
        self.log_path = os.path.join(self.PATH, "tomorrow_tip.log")
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 插件初始化,日志文件已创建\n")

    def update(self, cw_contexts):  # 自动更新部分
        super().update(cw_contexts)  # 调用父类更新方法
        schedule_name = cw_contexts.get("Schedule_Name", "")
        if schedule_name == "backup.json":
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到调休课表(backup.json),临时禁用通知\n")
            return

        current_time = cw_contexts.get("current_time", "")
        tip_time = self.settings.value("tip_time", "18:00:00")
        from datetime import datetime

        try:
            if not current_time.strip():
                current_time = datetime.now().strftime("%H:%M:%S")

            current_dt = datetime.strptime(current_time.strip(), "%H:%M:%S")
            tip_dt = datetime.strptime(tip_time, "%H:%M:%S")

            if current_dt.time() == tip_dt.time():
                today = dt.date.today()
                tomorrow = today + dt.timedelta(days=1)
                tomorrow_weekday = tomorrow.weekday()
                self.show_tomorrow_courses(tomorrow_weekday)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功触发定时提醒\n")

        except ValueError as e:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 时间格式错误: {e}\n")
            return

    def show_tomorrow_courses(self, tomorrow_weekday, is_test=False):
        """
        显示明日的课程信息
        参数:
            tomorrow_weekday: 明日的星期几(0-6,0表示星期一)
            is_test: 是否为测试通知,默认为False
        """
        import json

        if is_test:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 触发测试通知\n")

        schedule_name = self.cw_contexts.get("Schedule_Name", "")
        if not schedule_name:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 无法获取明日课程信息：未设置课程表\n")
            return

        schedule_path = os.path.join(self.cw_contexts.get("base_directory", ""), "config", "schedule", f"{schedule_name}")
        # 检查课程
        if not os.path.exists(schedule_path):
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 无法获取明日课程信息：课程表文件不存在 ({schedule_path})\n"
                )
            return

        try:
            with open(schedule_path, encoding="utf-8") as f:
                schedule_data = json.load(f)

            tomorrow_courses = []

            # 解析课表
            timeline = {}
            if "timeline" in schedule_data:
                if str(tomorrow_weekday) in schedule_data["timeline"] and schedule_data["timeline"][str(tomorrow_weekday)]:
                    timeline = schedule_data["timeline"][str(tomorrow_weekday)]
                elif "default" in schedule_data["timeline"]:
                    timeline = schedule_data["timeline"]["default"]

            schedule = None
            if "schedule" in schedule_data and str(tomorrow_weekday) in schedule_data["schedule"]:
                schedule = schedule_data["schedule"][str(tomorrow_weekday)]

            if not timeline or not schedule:
                title = "明日课程提醒"
                content = "明日没有课程安排"
                subtitle = "享受休息吧！"
                if is_test:
                    title = "测试 - " + title
                notification_duration = self.settings.value("notification_duration", 10000, type=int)
                self.method.send_notification(
                    state=4, title=title, content=content, subtitle=subtitle, duration=notification_duration
                )
                return

            part_times = {}
            if "part" in schedule_data:
                for part_id, part_info in schedule_data["part"].items():
                    if len(part_info) >= 2:
                        h, m = part_info[:2]
                        part_times[part_id] = dt.time(h, m)
            class_count = 0
            course_count = self.settings.value("course_count", 4, type=int)
            for item_name, _item_time in sorted(timeline.items()):
                if item_name.startswith("a"):
                    # 获取part编号
                    try:
                        part_num = int(item_name[1])
                        # 获取课程名称
                        if class_count < len(schedule):
                            course_name = schedule[class_count]
                            if course_name not in {"未添加", "暂无课程"}:
                                # 检查课程是否在排除列表中
                                excluded_courses_str = self.settings.value("excluded_courses", "")
                                excluded_courses = [c.strip() for c in excluded_courses_str.split(",") if c.strip()]

                                if course_name not in excluded_courses:
                                    tomorrow_courses.append(f"{course_name}")
                                    if len(tomorrow_courses) >= course_count:
                                        break
                                else:
                                    with open(self.log_path, "a", encoding="utf-8") as f:
                                        f.write(
                                            f'[{dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] 课程 "{course_name}" 在排除列表中,不显示\n'
                                        )
                        class_count += 1
                    except (ValueError, IndexError) as e:
                        with open(self.log_path, "a", encoding="utf-8") as f:
                            f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 解析课程数据错误: {e}\n")

            title = "明日课程提醒"
            if tomorrow_courses:
                content = " | ".join(tomorrow_courses)
                subtitle = "明日课程安排:"
            else:
                content = "明日没有课程安排"
                subtitle = "享受休息吧！"

            # 如果是测试通知,修改标题
            if is_test:
                title = "测试通知 - " + title

            # 获取通知显示时间
            notification_duration = self.settings.value("notification_duration", 10000, type=int)
            self.method.send_notification(
                state=4, title=title, content=content, subtitle=subtitle, duration=notification_duration
            )

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送通知,显示时间设置为: {notification_duration}毫秒({notification_duration // 1000}秒)\n"
                )

        except Exception as e:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取明日课程信息失败: {e}\n")


class Settings(SettingsBase):
    def __init__(self, plugin_path, parent=None):
        super().__init__(plugin_path, parent)
        uic.loadUi(f"{self.PATH}/settings.ui", self)  # 加载设置界面
        # 初始化设置
        self.settings = QSettings(f"{self.PATH}/config.ini", QSettings.IniFormat)

        # 检查当前课表名称
        self.is_backup_schedule = False
        if hasattr(self, "cw_contexts") and self.cw_contexts:
            schedule_name = self.cw_contexts.get("Schedule_Name", "")
            if schedule_name == "backup.json":
                self.is_backup_schedule = True
                # 显示警告信息
                msg_box = MessageBox(
                    "警告", "当前使用可能是调休课表(backup.json),通知已被临时禁用。\n请恢复原课表后再使用通知功能。", self
                )
                msg_box.yesButton.setText("确定")
                msg_box.cancelButton.setVisible(False)
                msg_box.exec()

        # 绑定设置
        self.enableTip.setChecked(self.settings.value("enable_tip", True, type=bool))
        # 如果是调休课表,禁用通知开关
        if self.is_backup_schedule:
            self.enableTip.setEnabled(False)
            self.enableTip.setToolTip("当前使用调休课表(backup.json),通知已临时禁用")

        self.SpinBox.setValue(self.settings.value("course_count", 4, type=int))
        self.timeEdit = self.findChild(TimePicker, "TimePicker")
        tip_time = self.settings.value("tip_time", "18:00:00")
        time_parts = tip_time.split(":")
        qtime = QTime(int(time_parts[0]), int(time_parts[1]), int(time_parts[2]))
        if self.timeEdit:
            self.timeEdit.setTime(qtime)
            self.timeEdit.setSecondVisible(True)
        self.viewLogButton = self.findChild(PrimaryPushButton, "viewLogButton")
        if self.viewLogButton:
            self.viewLogButton.clicked.connect(self.view_log)
        # 测试通知按钮
        self.testNotificationButton = self.findChild(PrimaryPushButton, "PrimaryPushButton")
        if self.testNotificationButton:
            self.testNotificationButton.clicked.connect(self.test_notification)
        # 排除课程
        self.excludedCoursesEdit = self.findChild(LineEdit, "excludedCoursesEdit")
        if self.excludedCoursesEdit:
            self.excludedCoursesEdit.setText(self.settings.value("excluded_courses", ""))
            self.excludedCoursesEdit.textChanged.connect(self.save_settings)
        # 显示时间(秒)
        self.notificationDurationSpinBox = self.findChild(SpinBox, "SpinBox_2")
        if self.notificationDurationSpinBox:
            # 从配置中读取毫秒值并转换为秒显示
            notification_duration_ms = self.settings.value("notification_duration", 10000, type=int)
            self.notificationDurationSpinBox.setValue(notification_duration_ms // 1000)
            self.notificationDurationSpinBox.valueChanged.connect(self.save_settings)

        self.timeEdit.timeChanged.connect(self.save_settings)
        self.enableTip.checkedChanged.connect(self.save_settings)
        self.SpinBox.valueChanged.connect(self.save_settings)

    def save_settings(self):
        """保存设置到配置文件"""
        # 通知开关
        if not hasattr(self, "is_backup_schedule") or not self.is_backup_schedule:
            self.settings.setValue("enable_tip", self.enableTip.isChecked())

        self.settings.setValue("course_count", self.SpinBox.value())
        # 时间
        if hasattr(self, "timeEdit"):
            time_str = self.timeEdit.time.toString("HH:mm:ss")
            self.settings.setValue("tip_time", time_str)
        # 排除课程
        if hasattr(self, "excludedCoursesEdit"):
            excluded_courses = self.excludedCoursesEdit.text()
            self.settings.setValue("excluded_courses", excluded_courses)
        # 显示时间
        if hasattr(self, "notificationDurationSpinBox"):
            notification_duration_seconds = self.notificationDurationSpinBox.value()
            notification_duration_ms = notification_duration_seconds * 1000
            self.settings.setValue("notification_duration", notification_duration_ms)

    def view_log(self):
        """查看日志"""
        # 修改为从插件目录读取日志
        self.log_path = os.path.join(self.PATH, "tomorrow_tip.log")
        log_content = "插件运行日志：\n\n"
        if os.path.exists(self.log_path):
            with open(self.log_path, encoding="utf-8") as f:
                log_content += f.read()
        else:
            log_content += "\n日志文件尚未生成"

        msg_box = MessageBox("插件日志", log_content, self)
        msg_box.yesButton.setText("确定")
        msg_box.cancelButton.setVisible(False)
        msg_box.exec()

    def test_notification(self):
        """测试通知功能"""
        if hasattr(self, "is_backup_schedule") and self.is_backup_schedule:
            msg_box = MessageBox(
                "测试通知", "当前使用可能是调休课表(backup.json),通知已被临时禁用。\n请恢复原课表后再使用通知功能。", self
            )
            msg_box.yesButton.setText("确定")
            msg_box.cancelButton.setVisible(False)
            msg_box.exec()
            return
        today = dt.date.today()
        # 计算明天星期(0-6,0=星期一)
        tomorrow = today + dt.timedelta(days=1)
        tomorrow_weekday = tomorrow.weekday()

        try:
            from plugin import p_loader

            plugin_name = "cw-tomorrow-tip"
            if plugin_name in p_loader.plugins_dict:
                plugin_instance = p_loader.plugins_dict[plugin_name]
                plugin_instance.show_tomorrow_courses(tomorrow_weekday, is_test=True)
                return

            log_path = os.path.join(self.PATH, "tomorrow_tip.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 测试通知：创建临时插件实例\n")
            # 创建临时插件
            plugin_instance = Plugin(
                self.cw_contexts if hasattr(self, "cw_contexts") else {}, self.method if hasattr(self, "method") else None
            )
            plugin_instance.PATH = self.PATH
            plugin_instance.log_path = log_path
            plugin_instance.show_tomorrow_courses(tomorrow_weekday, is_test=True)
            return

        except Exception as e:
            error_msg = f"测试通知失败: {e}"
            try:
                log_path = os.path.join(self.PATH, "tomorrow_tip.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}\n")
            except Exception as log_error:
                pass

        msg_box = MessageBox("测试通知", "无法发送测试通知,请确保插件已正确加载。", self)
        msg_box.yesButton.setText("确定")
        msg_box.cancelButton.setVisible(False)
        msg_box.exec()
