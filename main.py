"""
    这是一个示例插件
    Author: 君の名は

    Tips:
    若要在插件广场推送您的更新，请手动修改"plugin.json"的"version"版本号字段以被插件广场识别
"""
from PyQt5 import uic
from .ClassWidgets.base import PluginBase, SettingsBase  # 导入CW的基类


class Plugin(PluginBase):  # 插件类
    def __init__(self, cw_contexts, method):  # 初始化
        super().__init__(cw_contexts, method)  # 调用父类初始化方法
        """
        插件初始化，插件被执行时将会执行此部分的代码
        """

    def execute(self):  # 自启动执行部分
        """
        当 Class Widgets启动时，将会执行此部分的代码
        """
        print('Plugin Executed!')

    def update(self, cw_contexts):  # 自动更新部分
        """
            Class Widgets 会每1秒更新一次状态，同时也会调用此部分的代码。
            可在此部分插入动态更新的内容
        """
        super().update(cw_contexts)  # 调用父类更新方法


# 设置页（若无此需求，请删除此部分并将"__init__.py"中引用的本模块部分删除，并在"plugins.json"中把"settings"子块设为"false"）
class Settings(SettingsBase):
    def __init__(self, plugin_path, parent=None):
        super().__init__(plugin_path, parent)
        uic.loadUi(f'{self.PATH}/settings.ui', self)  # 加载设置界面
        """
        在这里写设置页面
        """
