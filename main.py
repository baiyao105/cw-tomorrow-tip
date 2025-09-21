import datetime as dt
import json
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from PyQt5 import uic
from PyQt5.QtCore import QSettings, QTime
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import (
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    SpinBox,
    TimePicker,
)


class PluginBase:
    """插件基类"""

    def __init__(self, cw_contexts: Dict[str, Any], method):
        self.cw_contexts = cw_contexts
        self.method = method
        self.PATH = Path(__file__).parent

    def execute(self):
        """插件启动时执行"""

    def update(self, cw_contexts: Dict[str, Any]):
        """更新插件状态"""
        self.cw_contexts = cw_contexts


class SettingsBase(QWidget):
    """设置基类"""

    def __init__(self, plugin_path=None, parent=None):
        super().__init__(parent)
        self.PATH = Path(plugin_path) if plugin_path else Path(__file__).parent
        self.settings = QSettings(str(self.PATH / "config.ini"), QSettings.IniFormat)


class Plugin(PluginBase):
    """明日课程提醒插件主类"""

    def __init__(self, cw_contexts: Dict[str, Any], method):
        super().__init__(cw_contexts, method)
        self.settings = QSettings(str(self.PATH / "config.ini"), QSettings.IniFormat)
        self.is_backup_schedule = False
        self.last_notification_key = None  # 记录上次通知的唯一标识

    def execute(self):
        """插件启动时执行"""
        try:
            if not self.settings.value("enable_tip", True, type=bool):
                logger.debug("提醒已禁用")
                return
            # schedule_name = self.cw_contexts.get("Schedule_Name", "")
            # if schedule_name == "backup.json":
            #     self.is_backup_schedule = True
            #     logger.warning("检测到调休课表,跳过通知")
            #     return
        except Exception as e:
            logger.error(f"插件启动失败: {e}")

    def update(self, cw_contexts: Dict[str, Any]):
        """更新插件状态"""
        super().update(cw_contexts)

        try:
            # 检查是否到达提醒时间
            current_time = dt.datetime.now().time()
            current_date = dt.date.today()
            self.settings.sync()
            tip_time_str = self.settings.value("tip_time", "18:00:00")
            tip_time = dt.datetime.strptime(tip_time_str, "%H:%M:%S").time()
            current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
            tip_seconds = tip_time.hour * 3600 + tip_time.minute * 60 + tip_time.second
            time_diff = abs(current_seconds - tip_seconds)
            # logger.debug(f"当前时间: {current_time}, 提醒时间: {tip_time}, 时间差: {time_diff}秒")
            notification_key = f"{current_date}_{tip_time_str}"
            if (
                time_diff <= 5  # 5秒时间窗口
                and self.settings.value("enable_tip", True, type=bool)
                and not self.is_backup_schedule
                and getattr(self, 'last_notification_key', None) != notification_key  # 防止同一时间重复通知
            ):
                logger.info(f"触发明日课程提醒 - 当前时间: {current_time}, 提醒时间: {tip_time}")
                tomorrow = dt.date.today() + dt.timedelta(days=1)
                tomorrow_weekday = tomorrow.weekday()
                self.show_tomorrow_courses(tomorrow_weekday)
                self.last_notification_key = notification_key

        except Exception as e:
            logger.error(f"更新插件状态失败: {e}")
            logger.error(traceback.format_exc())

    def show_tomorrow_courses(self, tomorrow_weekday: int, is_test: bool = False):
        """
        显示明日的课程信息

        Args:
            tomorrow_weekday: 明日的星期几(0-6,0表示星期一)
            is_test: 是否为测试通知
        """
        if is_test:
            logger.debug("测试通知")
        schedule_name = self.cw_contexts.get("Schedule_Name", "")
        if not schedule_name:
            logger.error("无法获取课程信息(未获得课程表)")
            return

        schedule_path = Path(self.cw_contexts.get("base_directory", "")) / "config" / "schedule" / schedule_name
        if not schedule_path.exists():
            logger.error(f"课表文件不存在: {schedule_path}")
            return

        try:
            schedule_data = self._load_schedule_data_from_path(schedule_path)
            tomorrow_courses = self._extract_tomorrow_courses(schedule_data, tomorrow_weekday)
            self._send_notification_legacy(tomorrow_courses, is_test)  # 发送通知
        except Exception as e:
            logger.error(f"获取课程信息失败: {e}")

    def check_schedule(self) -> None:
        """检查课表,发送提醒"""
        try:
            settings = self._load_settings()
            if not settings.get("enabled", True):
                return

            # logger.debug(f"设置: {settings}")

            now = datetime.now()
            reminder_time = settings.get("reminder_time", "21:00")
            try:
                hour, minute = map(int, reminder_time.split(":"))
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # logger.debug(f"当前时间: {now.strftime('%H:%M')}, 提醒时间: {reminder_time}")
            except (ValueError, AttributeError):
                logger.error(f"提醒时间格式无效: {reminder_time}")
                return

            # 检查是否到达提醒时间(允许1分钟误差)
            time_diff = abs((now - target_time).total_seconds())
            # logger.debug(f"时间差: {time_diff} 秒")
            if time_diff > 60:
                return
            tomorrow_classes = self._get_tomorrow_classes()
            if not tomorrow_classes:
                logger.debug("明日无课程")
                return
            logger.debug(f"获取到明日课程: {len(tomorrow_classes)} 门")
            for i, cls in enumerate(tomorrow_classes):
                logger.debug(f"  {i + 1}. {cls.get('name', '未知')} ({cls.get('time', '未知时间')})")
            self._send_notification(tomorrow_classes, settings)

        except Exception as e:
            logger.error(f"检查课表时发生错误: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")

    def _load_settings(self) -> Dict[str, Any]:
        """加载插件设置"""
        try:
            settings_file = Path(self.PATH) / "settings.json"
            if settings_file.exists():
                with open(settings_file, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
        return {
            "enabled": True,
            "reminder_time": "21:00",
            "show_all_classes": True,
            "show_class_time": True,
            "custom_message": "",
        }

    def _get_tomorrow_classes(self) -> List[Dict[str, Any]]:
        """获取明日课程安排"""
        try:
            tomorrow = datetime.now() + timedelta(days=1)
            weekday = tomorrow.weekday()  # 0=周一, 6=周日
            # logger.info(f"获取明日课程: {tomorrow.strftime('%Y-%m-%d')} (周{weekday + 1})")
            schedule_data = self._load_schedule_data()
            if not schedule_data:
                logger.warning("课表数据为空")
                return []

            # logger.debug(f"数据键: {list(schedule_data.keys())}")
            if self._is_v2_format(schedule_data):
                logger.debug("使用V2格式解析课表")
                return self._parse_v2_schedule(schedule_data, weekday)
            logger.debug("使用V1格式解析课表")
            return self._parse_v1_schedule(schedule_data, weekday)

        except Exception as e:
            logger.error(f"获取明日课程失败: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _is_v2_format(self, schedule_data: Dict[str, Any]) -> bool:
        """判断是否为V2格式课表"""
        return "timeline" in schedule_data and "schedule" in schedule_data

    def _parse_v1_schedule(
        self, schedule_data: Dict[str, Any], weekday: int
    ) -> List[Dict[str, Any]]:
        """解析V1格式课表(什么鬼"""
        try:
            classes = []
            tomorrow_weekday = weekday
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
                logger.debug("V1格式: 明日没有课程")
                return []
            part_times = {}
            if "part" in schedule_data:
                for part_id, part_info in schedule_data["part"].items():
                    if len(part_info) >= 2:
                        h, m = part_info[:2]
                        part_times[part_id] = f"{h:02d}:{m:02d}"
            class_count = 0
            excluded_courses = self._get_excluded_courses()
            for item_name, _item_time in sorted(timeline.items()):
                if item_name.startswith("a"):  # 课程时间段
                    try:
                        part_num = int(item_name[1])  # 获取part编号
                        if class_count < len(schedule):
                            course_name = schedule[class_count]
                            if self._is_valid_course(course_name, excluded_courses):
                                time_info = part_times.get(str(part_num), f"第{part_num}节")
                                classes.append({
                                    "name": course_name,
                                    "time": time_info
                                })
                        class_count += 1
                    except (ValueError, IndexError) as e:
                        logger.warning(f"课程数据错误: {e}")
                        continue
            return classes

        except Exception as e:
            logger.error(f"V1格式解析失败: {e}")
            return []

    def _load_schedule_data(self) -> Optional[Dict[str, Any]]:
        """加载课表数据"""
        try:
            schedule_name = self.cw_contexts.get("Schedule_Name", "")
            if not schedule_name:
                logger.warning("未设置课表文件名")
                return None
            base_dir = self.cw_contexts.get("base_directory", "")
            schedule_path = Path(base_dir) / "config" / "schedule" / schedule_name
            # logger.debug(f"课表文件路径: {schedule_path}")

            if not schedule_path.exists():
                logger.warning(f"课表文件不存在: {schedule_path}")
                # schedule_dir = Path(base_dir) / "config" / "schedule"
                # if schedule_dir.exists():
                #     files = list(schedule_dir.iterdir())
                #     logger.debug(f"schedule目录下的文件: {files}")
                return None
            with open(schedule_path, encoding="utf-8") as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"加载课表数据失败: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None

    def _is_valid_course(
        self, course_name: str, excluded_courses: Optional[List[str]] = None
    ) -> bool:
        """检查课程是否有效"""
        if not course_name:
            return False

        default_excluded = ["未添加", "暂无课程", "", "无课程"]
        if excluded_courses is None:
            excluded_courses = []
        all_excluded = default_excluded + excluded_courses
        return course_name not in all_excluded

    def _parse_v2_schedule(
        self, schedule_data: Dict[str, Any], weekday: int
    ) -> List[Dict[str, Any]]:
        """解析V2格式课表,按照主程序逻辑"""
        try:
            # logger.info(f"开始解析目标日期: 周{weekday + 1}")
            classes = []

            timeline = self._get_timeline_for_day(schedule_data, weekday)
            schedule = self._get_schedule_for_day(schedule_data, weekday)

            # logger.info(f"获取到时间线数量: {len(timeline)}")
            # logger.info(f"获取到课程数量: {len(schedule)}")

            if not timeline or not schedule:
                logger.warning("时间线或课程为空")
                return []

            excluded_courses = self._get_excluded_courses()
            logger.info(f"排除课程列表: {excluded_courses}")
            for i, (time_slot, course_name) in enumerate(zip(timeline, schedule)):
                # logger.debug(f"解析第{i + 1}节课: 时间={time_slot}, 课程={course_name}")
                if not course_name or course_name in excluded_courses:
                    # logger.debug(f"跳过课程: {course_name} (空课程或在排除列表中)")
                    continue
                if not self._is_valid_course(course_name, excluded_courses):
                    # logger.debug(f"⏭跳过无效课程: {course_name}")
                    continue
                class_info = {
                    "name": course_name,
                    "time": f"{time_slot[0]}-{time_slot[1]}",
                    "period": i + 1,
                    "start_time": time_slot[0],
                    "end_time": time_slot[1],
                }
                classes.append(class_info)

            return classes

        except Exception as e:
            logger.error(f"解析失败: {e}")
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _send_notification(self, classes: List[Dict[str, Any]], settings: Dict[str, Any]) -> None:
        """发送课程提醒通知"""
        try:
            if not classes:
                return
            title = "明日课程提醒"
            if settings.get("custom_message"):
                content = settings["custom_message"]
            else:
                class_list = []
                for cls in classes:
                    if settings.get("show_class_time", True):
                        class_list.append(f"{cls['start_time']} {cls['name']}")
                    else:
                        class_list.append(cls["name"])
                content = f"明日共有 {len(classes)} 节课程: \n" + "\n".join(class_list)
            self.method.send_notification(
                state=1,
                lesson_name="明日课程",
                title=title,
                subtitle=f"共 {len(classes)} 节课",
                content=content,
                duration=5000,
            )

            logger.info(f"已发送明日课程提醒,共 {len(classes)} 节课")

        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    def _show_tomorrow_courses(self, tomorrow_weekday: int, is_test: bool = False):
        """
        显示明日的课程信息

        Args:
            tomorrow_weekday: 明日的星期几(0-6,0表示星期一)
            is_test: 是否为测试通知
        """
        if is_test:
            logger.info("触发测试通知")
        schedule_name = self.cw_contexts.get("Schedule_Name", "")
        if not schedule_name:
            logger.error("无法获取课程信息(未设置课程表)")
            return
        schedule_path = Path(self.cw_contexts.get("base_directory", "")) / "config" / "schedule" / schedule_name
        if not schedule_path.exists():
            logger.error(f"课程表文件不存在: {schedule_path}")
            return

        try:
            schedule_data = self._load_schedule_data_from_path(schedule_path)
            tomorrow_courses = self._extract_tomorrow_courses(schedule_data, tomorrow_weekday)
            self._send_notification_legacy(tomorrow_courses, is_test)

        except Exception as e:
            logger.error(f"获取明日课程信息失败: {e}")

    def _load_schedule_data_from_path(self, schedule_path: str) -> Dict[str, Any]:
        """从指定路径加载课表数据"""
        with open(schedule_path, encoding="utf-8") as f:
            return json.load(f)

    def _extract_tomorrow_courses(self, schedule_data: Dict[str, Any], weekday: int) -> List[str]:
        """
        从课表数据中提取明日课程

        Args:
            schedule_data: 课表数据
            weekday: 星期几(0-6)

        Returns:
            明日课程列表
        """
        tomorrow_courses = []
        timeline = self._get_timeline_for_day(schedule_data, weekday)
        schedule = self._get_schedule_for_day(schedule_data, weekday)
        if not timeline or not schedule:
            logger.info("明日没有课程")
            return []

        course_count = self.settings.value("course_count", 4, type=int)
        excluded_courses = self._get_excluded_courses()
        class_index = 0
        for timeline_item in timeline:
            if len(timeline_item) >= 4:
                is_break, part_id, item_index, duration = timeline_item[:4]
                # 只处理课程
                if not is_break and class_index < len(schedule):
                    course_name = schedule[class_index]
                    if self._is_valid_course(course_name, excluded_courses):
                        tomorrow_courses.append(course_name)
                        # logger.debug(f"添加课程: {course_name}")
                        if len(tomorrow_courses) >= course_count:
                            break
                    # else:
                    #     logger.debug(f"课程 '{course_name}' 在排除列表中或为无效课程")
                    class_index += 1

        return tomorrow_courses

    def _get_timeline_for_day(self, schedule_data: Dict[str, Any], weekday: int) -> List[List]:
        """获取指定日期的时间线,按照主程序逻辑"""
        try:
            is_even_week = self._is_even_week()
            timeline_key = "timeline_even" if is_even_week else "timeline"
            # logger.debug(
            #     f"获取时间线: weekday={weekday}, is_even_week={is_even_week}, timeline_key={timeline_key}"
            # )
            timeline_data = schedule_data.get(timeline_key, {})
            # logger.debug(f"时间线数据键: {list(timeline_data.keys())}")
            weekday_str = str(weekday)
            if timeline_data.get(weekday_str):
                # logger.debug(
                #     f"找到周{weekday}的时间线数据,长度: {len(timeline_data[weekday_str])}"
                # )
                return timeline_data[weekday_str]
            if timeline_data.get("default"):
                # logger.debug(f"使用默认时间线数据,长度: {len(timeline_data['default'])}")
                return timeline_data["default"]
            logger.warning(f"{timeline_key}中未找到周{weekday}的时间线数据")
            fallback_key = "timeline" if is_even_week else "timeline_even"
            fallback_data = schedule_data.get(fallback_key, {})
            if fallback_data.get(weekday_str):
                logger.info(
                    f"使用{fallback_key}中周{weekday}的时间线数据,长度: {len(fallback_data[weekday_str])}"
                )
                return fallback_data[weekday_str]
            if fallback_data.get("default"):
                logger.debug(
                    f"使用{fallback_key}的默认时间线数据,长度: {len(fallback_data['default'])}"
                )
                return fallback_data["default"]
            for day_key, day_timeline in timeline_data.items():
                if day_timeline and day_key != "default":
                    logger.debug(f"发现周{day_key}有时间线数据,长度: {len(day_timeline)}")

            return []
        except Exception as e:
            logger.error(f"获取时间线失败: {e}")
            return []

    def _get_schedule_for_day(self, schedule_data: Dict[str, Any], weekday: int) -> List[str]:
        """获取指定日期的课程安排,按照主程序逻辑"""
        try:
            # 判断单双周
            is_even_week = self._is_even_week()
            schedule_key = "schedule_even" if is_even_week else "schedule"
            schedule_data_dict = schedule_data.get(schedule_key, {})
            weekday_str = str(weekday)
            if schedule_data_dict.get(weekday_str):
                return schedule_data_dict[weekday_str]
                # logger.debug(f"找到周{weekday}的课程安排,数量: {len(courses)}")
                # logger.debug(f"课程列表: {courses}")
            logger.warning(f"{schedule_key}中未找到周{weekday}的课程,尝试使用另一个课程安排")
            fallback_key = "schedule" if is_even_week else "schedule_even"
            fallback_data = schedule_data.get(fallback_key, {})
            if fallback_data.get(weekday_str):
                courses = fallback_data[weekday_str]
                logger.info(f"使用{fallback_key}中周{weekday}的课程安排,数量: {len(courses)}")
                # logger.debug(f"课程列表: {courses}")
                return courses
            for day_key, day_courses in schedule_data_dict.items():
                if day_courses:
                    logger.info(f"发现周{day_key}有课程,数量: {len(day_courses)}")

            return []
        except Exception as e:
            logger.error(f"获取课程安排失败: {e}")
            return []

    def _is_even_week(self) -> bool:
        """判断是否为双周"""
        try:
            # 尝试从主程序获取单双周信息
            if hasattr(self, "cw_contexts") and self.cw_contexts:
                try:
                    main_path = Path(__file__).parent.parent.parent
                    if str(main_path) not in sys.path:
                        sys.path.insert(0, str(main_path))
                    from file import config_center  # noqa
                    temp_schedule = config_center.read_conf('Temp', 'set_schedule')
                    if temp_schedule not in ('', None):
                        week_type = int(temp_schedule)
                        return week_type == 1  # 1表示双周
                    start_date_str = config_center.read_conf('Date', 'start_date')
                    if start_date_str not in ('', None):
                        try:
                            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                            today = dt.date.today()
                            week_num = (today - start_date).days // 7 + 1
                            return week_num % 2 == 0  # 偶数周为双周
                        except (ValueError, TypeError) as e:
                            logger.warning(f"解析开学日期失败: {e}")
                except ImportError as e:
                    logger.debug(f"无法导入主程序配置模块: {e}")
                except Exception as e:
                    logger.debug(f"获取主程序单双周配置失败: {e}")
            today = dt.date.today()
            week_number = today.isocalendar()[1]
            return week_number % 2 == 0

        except Exception as e:
            logger.error(f"判断单双周时出错: {e}")
            return False

    def _get_excluded_courses(self) -> List[str]:
        """获取排除的课程列表"""
        excluded_courses_str = self.settings.value("excluded_courses", "")
        return [c.strip() for c in excluded_courses_str.split(",") if c.strip()]

    def _send_notification_legacy(self, courses: List[str], is_test: bool = False):
        """发送通知"""
        title = "明日课程提醒"
        if is_test:
            title = "测试通知 - " + title
        if courses:
            content = " | ".join(courses)
            subtitle = "明日课程安排:"
        else:
            content = "明日没有课程安排"
            subtitle = "享受休息吧!"
        notification_duration = self.settings.value("notification_duration", 10000, type=int)
        try:
            self.method.send_notification(
                state=4,
                title=title,
                content=content,
                subtitle=subtitle,
                duration=notification_duration,
            )
            # logger.info(f"通知发送成功,显示时间: {notification_duration}ms")
        except Exception as e:
            logger.error(f"发送通知失败: {e}")


class Settings(SettingsBase):
    def __init__(self, plugin_path, parent=None):
        super().__init__(plugin_path, parent)
        uic.loadUi(f"{self.PATH}/settings.ui", self)
        self.settings = QSettings(f"{self.PATH}/config.ini", QSettings.IniFormat)
        # 检查当前课表名称
        # self.is_backup_schedule = False
        # if hasattr(self, "cw_contexts") and self.cw_contexts:
        #     schedule_name = self.cw_contexts.get("Schedule_Name", "")
        #     if schedule_name == "backup.json":
        #         self.is_backup_schedule = True
        #         msg_box = MessageBox(
        #             "警告",
        #             "当前使用可能是调休课表(backup.json),通知已被临时禁用。\n请恢复原课表后再使用通知功能。",
        #             self,
        #         )
        #         msg_box.yesButton.setText("确定")
        #         msg_box.cancelButton.setVisible(False)
        #         msg_box.exec()

        self.enableTip.setChecked(self.settings.value("enable_tip", True, type=bool))
        # # 如果是调休课表,禁用通知开关
        # if self.is_backup_schedule:
        #     self.enableTip.setEnabled(False)
        #     self.enableTip.setToolTip("当前使用调休课表(backup.json),通知已临时禁用")
        self.SpinBox.setValue(self.settings.value("course_count", 4, type=int))
        self.timeEdit = self.findChild(TimePicker, "TimePicker")
        tip_time = self.settings.value("tip_time", "18:00:00")
        time_parts = tip_time.split(":")
        qtime = QTime(int(time_parts[0]), int(time_parts[1]), int(time_parts[2]))
        if self.timeEdit:
            self.timeEdit.setTime(qtime)
            self.timeEdit.setSecondVisible(True)
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
        self.timeEdit.timeChanged.connect(self.save_settings)
        self.enableTip.checkedChanged.connect(self.save_settings)
        self.SpinBox.valueChanged.connect(self.save_settings)

    def save_settings(self):
        """保存设置到配置文件"""
        if not hasattr(self, "is_backup_schedule") or not self.is_backup_schedule:
            self.settings.setValue("enable_tip", self.enableTip.isChecked())
        self.settings.setValue("course_count", self.SpinBox.value())
        if hasattr(self, "timeEdit"):
            time_str = self.timeEdit.time.toString("HH:mm:ss")
            self.settings.setValue("tip_time", time_str)
        if hasattr(self, "excludedCoursesEdit"):
            excluded_courses = self.excludedCoursesEdit.text()
            self.settings.setValue("excluded_courses", excluded_courses)
        if hasattr(self, "notificationDurationSpinBox"):
            notification_duration_seconds = self.notificationDurationSpinBox.value()
            notification_duration_ms = notification_duration_seconds * 1000
            self.settings.setValue("notification_duration", notification_duration_ms)
        self.settings.sync()

    def test_notification(self):
        """测试通知功能"""
        # if hasattr(self, "is_backup_schedule") and self.is_backup_schedule:
        #     msg_box = MessageBox(
        #         "测试通知",
        #         "当前使用可能是调休课表(backup.json),通知已被临时禁用。\n请恢复原课表后再使用通知功能。",
        #         self,
        #     )
        #     msg_box.yesButton.setText("确定")
        #     msg_box.cancelButton.setVisible(False)
        #     msg_box.exec()
        #     return
        today = dt.date.today()
        # 计算明天星期(0-6,0=星期一)
        tomorrow = today + dt.timedelta(days=1)
        tomorrow_weekday = tomorrow.weekday()

        try:
            from plugin import p_loader  # noqa

            plugin_name = "cw-tomorrow-tip"
            if plugin_name in p_loader.plugins_dict:
                plugin_instance = p_loader.plugins_dict[plugin_name]
                plugin_instance.show_tomorrow_courses(tomorrow_weekday, is_test=True)
                return
            plugin_instance = Plugin(
                self.cw_contexts if hasattr(self, "cw_contexts") else {},
                self.method if hasattr(self, "method") else None,
            )
            plugin_instance.PATH = self.PATH
            plugin_instance.show_tomorrow_courses(tomorrow_weekday, is_test=True)
            return
        except Exception as e:
            error_msg = f"测试通知失败: {e}"
            logger.error(error_msg)

        msg_box = MessageBox("测试通知", "无法发送测试通知", self)
        msg_box.yesButton.setText("确定")
        msg_box.cancelButton.setVisible(False)
        msg_box.exec()
