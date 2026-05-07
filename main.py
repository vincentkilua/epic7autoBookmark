import os
import sys
from datetime import datetime
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QSettings
from adbutils import adb, AdbDevice
from numpy import asarray
import aircv
import cv2

# ==========================================
# 1. 資源路徑處理
# ==========================================

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

def resource_path(relative_path):
    """ 取得資源的絕對路徑 (用於內建圖片、Icon) """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def normalize_screenshot(screenshot):
    h, w = screenshot.shape[:2]
    if w == TARGET_WIDTH and h == TARGET_HEIGHT:
        return screenshot
    return cv2.resize(screenshot, (TARGET_WIDTH, TARGET_HEIGHT))

# ==========================================
# UI 語言翻譯字典
# ==========================================

UI_LANG = {
    "zh-TW": {
        "tab_function": "功能",
        "tab_help": "說明",
        "tab_stats": "統計",
        "label_gold": "金幣:",
        "label_stone": "天空石:",
        "group_stop": "停止條件",
        "radio_cov": "達到聖約次數",
        "radio_mys": "達到神秘次數",
        "radio_stone": "消耗天空石數量",
        "label_debug": "除錯訊息:",
        "group_adb": "ADB 連線設定",
        "label_host": "位址:",
        "label_port": "埠號:",
        "label_lang": "遊戲語言:",
        "label_ui_lang": "介面語言:",
        "btn_start": "開始執行",
        "btn_stop": "停止執行",
        "btn_reset": "重置統計",
        "help_html": (
            '<h3>使用說明</h3>'
            '<ul>'
            '<li><b>第一步：</b>在右側面板設定 ADB 位址、埠號與遊戲語言。</li>'
            '<li><b>第二步：</b>輸入當前遊戲中的金幣與天空石餘額。</li>'
            '<li><b>第三步：</b>選擇要停止的條件（例如刷到 50 次聖約後停止）。</li>'
            '</ul>'
            '<p>期望值計算公式：$$E = \\frac{\\text{總消耗天空石}}{\\text{獲得書籤次數}}$$</p>'
            '<p><i>設定值會在關閉程式時自動儲存，下次啟動無需重新輸入。</i></p>'
        ),
        "confirm_reset_title": "確認重置",
        "confirm_reset_msg": "確定要清除所有累計統計資料嗎？",
        "log_start": "🚀 啟動腳本...",
        "log_stop": "🛑 使用者手動停止執行",
        "log_reset": "🔄 累計統計已重置",
        "stats_sessions": "總執行次數:",
        "stats_refreshes": "總刷新次數:",
        "stats_stones": "總消耗天空石:",
        "stats_gold": "總消耗金幣:",
        "stats_covenant": "獲得聖約書籤:",
        "stats_mystic": "獲得神秘書籤:",
        "stats_ev_cov": "累計聖約期望值:",
        "stats_ev_mys": "累計神秘期望值:",
        "btn_test": "測試連線",
        "test_ok": "✅ 連線成功，截圖已擷取",
        "test_fail": "❌ 連線失敗",
        "label_refresh_count": "刷新次數:",
    },
    "en": {
        "tab_function": "Function",
        "tab_help": "Help",
        "tab_stats": "Stats",
        "label_gold": "Gold:",
        "label_stone": "Skystones:",
        "group_stop": "Stop Condition",
        "radio_cov": "By Covenant Count",
        "radio_mys": "By Mystic Count",
        "radio_stone": "By Skystones Spent",
        "label_debug": "Debug Log:",
        "group_adb": "ADB Settings",
        "label_host": "Address:",
        "label_port": "Port:",
        "label_lang": "Game Language:",
        "label_ui_lang": "UI Language:",
        "btn_start": "Start",
        "btn_stop": "Stop",
        "btn_reset": "Reset Stats",
        "help_html": (
            '<h3>Instructions</h3>'
            '<ul>'
            '<li><b>Step 1:</b> Configure ADB address, port, and game language in the right panel.</li>'
            '<li><b>Step 2:</b> Enter your current in-game gold and skystone amounts.</li>'
            '<li><b>Step 3:</b> Choose a stop condition (e.g. stop after 50 covenant bookmarks).</li>'
            '</ul>'
            '<p>Expected value formula: $$E = \\frac{\\text{Total Skystones Spent}}{\\text{Bookmarks Found}}$$</p>'
            '<p><i>Settings are auto-saved on close and restored on next launch.</i></p>'
        ),
        "confirm_reset_title": "Confirm Reset",
        "confirm_reset_msg": "Clear all cumulative statistics?",
        "log_start": "🚀 Script started...",
        "log_stop": "🛑 Manually stopped",
        "log_reset": "🔄 Cumulative stats reset",
        "stats_sessions": "Total Sessions:",
        "stats_refreshes": "Total Refreshes:",
        "stats_stones": "Total Skystones:",
        "stats_gold": "Total Gold:",
        "stats_covenant": "Covenant Found:",
        "stats_mystic": "Mystic Found:",
        "stats_ev_cov": "Covenant EV:",
        "stats_ev_mys": "Mystic EV:",
        "btn_test": "Test Connection",
        "test_ok": "✅ Connection OK, screenshot captured",
        "test_fail": "❌ Connection failed",
        "label_refresh_count": "Refreshes:",
    },
}

# ==========================================
# 2. Worker 執行緒 (強化統計與回報邏輯)
# ==========================================

class worker(QtCore.QThread):
    isStart = QtCore.pyqtSignal()
    isFinish = QtCore.pyqtSignal(str) # 改為傳回結算字串
    isError = QtCore.pyqtSignal(str)
    emitLog = QtCore.pyqtSignal(str)
    emitDebug = QtCore.pyqtSignal(str)
    emitMoney = QtCore.pyqtSignal(str)
    emitStone = QtCore.pyqtSignal(str)
    emitRefreshCount = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.reset_stats()

    def reset_stats(self):
        """ 重置統計數據 """
        self.refreshTime = 0
        self.covenantFoundCount = 0
        self.mysticFoundCount = 0
        self.totalMoneySpent = 0
        self.orig_w = TARGET_WIDTH
        self.orig_h = TARGET_HEIGHT

    def to_device(self, x, y):
        scale_x = self.orig_w / TARGET_WIDTH
        scale_y = self.orig_h / TARGET_HEIGHT
        return int(x * scale_x), int(y * scale_y)

    def log(self, msg):
        self.emitLog.emit(f"[{datetime.now():%H:%M:%S}] {msg}")

    def debug(self, msg):
        self.emitDebug.emit(f"[{datetime.now():%H:%M:%S}] {msg}")

    def setVariable(self, startMode, expectNum, moneyNum, stoneNum, config, cumulative):
        self.startMode = startMode
        self.expectNum = expectNum
        self.moneyNum = moneyNum
        self.stoneNum = stoneNum
        self.config = config
        self.cumulative = cumulative
        self.reset_stats()

    def handle_buy_button(self, device, buyButton, money_cost, type_name):
        self.debug(f"  ⏳ 等待購買視窗 (1.2s)...")
        QtCore.QThread.msleep(1200)
        buy_screenshot = normalize_screenshot(asarray(device.screenshot()))
        buyLoc = aircv.find_template(buy_screenshot, buyButton, 0.8)
        self.debug(f"  🔍 偵測購買按鈕: {'找到' if buyLoc else '未找到'}")

        if buyLoc:
            res = buyLoc["result"]
            dx, dy = self.to_device(res[0], res[1])
            self.debug(f"  點擊購買按鈕: ({dx}, {dy})")
            device.click(dx, dy)
            QtCore.QThread.msleep(800)

            self.moneyNum -= money_cost
            self.totalMoneySpent += money_cost
            self.emitMoney.emit(str(self.moneyNum))

            if type_name == "聖約": self.covenantFoundCount += 1
            else: self.mysticFoundCount += 1

            if (self.startMode == 1 and type_name == "聖約") or (self.startMode == 2 and type_name == "神秘"):
                self.expectNum -= 1

            self.log(f"✅ 買入【{type_name}】(刷新{self.refreshTime}次)，累計: 聖約x{self.covenantFoundCount}, 神秘x{self.mysticFoundCount}")
            return True
        self.debug(f"  ⚠️ 未找到購買按鈕，跳過")
        return False

    def handle_refresh_button(self, device, refreshButton, refreshYesButton):
        screenshot = normalize_screenshot(asarray(device.screenshot()))
        refreshLoc = aircv.find_template(screenshot, refreshButton, 0.9)
        self.debug(f"  🔍 偵測刷新按鈕: {'找到' if refreshLoc else '未找到'}")
        if refreshLoc:
            res = refreshLoc["result"]
            dx, dy = self.to_device(res[0], res[1])
            self.debug(f"  點擊刷新按鈕: ({dx}, {dy})")
            device.click(dx, dy)
            QtCore.QThread.msleep(800)

            confirm_screenshot = normalize_screenshot(asarray(device.screenshot()))
            yesLoc = aircv.find_template(confirm_screenshot, refreshYesButton, 0.9)
            self.debug(f"  🔍 偵測確認按鈕: {'找到' if yesLoc else '未找到'}")
            if yesLoc:
                dx, dy = self.to_device(yesLoc["result"][0], yesLoc["result"][1])
                device.click(dx, dy)
                self.stoneNum -= 3
                self.refreshTime += 1
                self.emitStone.emit(str(self.stoneNum))

                if self.startMode == 3:
                    self.expectNum -= 3

                self.emitRefreshCount.emit(str(self.refreshTime))
                self.debug(f"🔄 第 {self.refreshTime} 次更新商店...")
                return True
            self.debug(f"  ⚠️ 確認按鈕未找到")
        return False

    def run(self):
        self.isStart.emit()
        try:
            adb_addr = self.config.get("adb_addr", "127.0.0.1:5555")
            e7_lang = self.config.get("e7_language", "tw")
            
            self.log(f"🔌 正在連接到 ADB: {adb_addr}")
            adb.connect(adb_addr, timeout=10)
            device = adb.device(serial=adb_addr)
            self.log("✅ ADB 連線成功")

            self.debug("📷 載入模板圖片...")
            covenant_img = aircv.imread(resource_path("img/covenantLocation.png"))
            mystic_img = aircv.imread(resource_path("img/mysticLocation.png"))
            buy_img = aircv.imread(resource_path(f"img/buyButton-{e7_lang}.png"))
            re_img = aircv.imread(resource_path("img/refreshButton.png"))
            re_yes_img = aircv.imread(resource_path(f"img/refreshYesButton-{e7_lang}.png"))
            self.debug(f"✅ 模板載入完成 (語言: {e7_lang})")

            self.emitRefreshCount.emit("0")
            needRefresh = False
            loopCount = 0

            while self.expectNum > 0 and self.moneyNum > 280000 and self.stoneNum >= 3:
                loopCount += 1
                self.debug(f"---- 循環 #{loopCount} ----")
                self.debug(f"📸 擷取畫面...")
                raw = asarray(device.screenshot())
                self.orig_h, self.orig_w = raw.shape[:2]
                if self.orig_w != TARGET_WIDTH or self.orig_h != TARGET_HEIGHT:
                    self.debug(f"  ⚠️ 畫面尺寸 {self.orig_w}x{self.orig_h} → 調整至 {TARGET_WIDTH}x{TARGET_HEIGHT}")
                screenshot = normalize_screenshot(raw)

                # 檢查聖約
                covenant_match = aircv.find_template(screenshot, covenant_img, 0.9)
                self.debug(f"🔍 偵測聖約: {'找到' if covenant_match else '未找到'}")
                if covenant_match:
                    loc = covenant_match["result"]
                    dx, dy = self.to_device(loc[0] + 800, loc[1] + 40)
                    self.debug(f"  點擊位置: ({dx}, {dy})")
                    device.click(dx, dy)
                    self.handle_buy_button(device, buy_img, 184000, "聖約")

                # 檢查神秘
                screenshot = normalize_screenshot(asarray(device.screenshot()))
                mystic_match = aircv.find_template(screenshot, mystic_img, 0.9)
                self.debug(f"🔍 偵測神秘: {'找到' if mystic_match else '未找到'}")
                if mystic_match:
                    loc = mystic_match["result"]
                    dx, dy = self.to_device(loc[0] + 800, loc[1] + 40)
                    self.debug(f"  點擊位置: ({dx}, {dy})")
                    device.click(dx, dy)
                    self.handle_buy_button(device, buy_img, 280000, "神秘")

                if needRefresh:
                    self.debug("🔄 嘗試刷新商店...")
                    if self.handle_refresh_button(device, re_img, re_yes_img):
                        needRefresh = False
                        QtCore.QThread.msleep(1000)
                    else:
                        self.debug("⚠️ 刷新按鈕未找到")
                else:
                    self.debug("👇 向下滑動...")
                    x1, y1 = self.to_device(1400, 500)
                    x2, y2 = self.to_device(1400, 200)
                    device.swipe(x1, y1, x2, y2, 0.1)
                    needRefresh = True
                    QtCore.QThread.msleep(800)

            total_stones = self.refreshTime * 3

            cum_stones = self.cumulative["total_stones"] + total_stones
            cum_cov = self.cumulative["total_covenant"] + self.covenantFoundCount
            cum_mys = self.cumulative["total_mystic"] + self.mysticFoundCount
            ses_ev_cov = total_stones / self.covenantFoundCount if self.covenantFoundCount > 0 else 0
            ses_ev_mys = total_stones / self.mysticFoundCount if self.mysticFoundCount > 0 else 0
            cum_ev_cov = cum_stones / cum_cov if cum_cov > 0 else 0
            cum_ev_mys = cum_stones / cum_mys if cum_mys > 0 else 0

            summary = (
                f"===== 結算統計 =====\n"
                f"🔹 商店刷新總數: {self.refreshTime} 次\n"
                f"💎 消耗天空石: {total_stones} 個\n"
                f"💰 消耗金幣: {self.totalMoneySpent:,} 元\n"
                f"--------------------\n"
                f"🔖 獲得聖約書籤: {self.covenantFoundCount} 次\n"
                f"🔖 獲得神秘書籤: {self.mysticFoundCount} 次\n"
                f"--------------------\n"
                f"📈 聖約期望值: {ses_ev_cov:.2f} 石/次\n"
                f"📈 神秘期望值: {ses_ev_mys:.2f} 石/次\n"
                f"--------------------\n"
                f"📈 累計聖約期望值: {cum_ev_cov:.2f} 石/次 (共 {cum_cov} 次)\n"
                f"📈 累計神秘期望值: {cum_ev_mys:.2f} 石/次 (共 {cum_mys} 次)"
            )
            self.isFinish.emit(summary)

        except Exception as e:
            self.isError.emit(str(e))

# ==========================================
# 3. UI 介面
# ==========================================

class Ui_Main(object):
    # -- translation helpers --
    def L(self, key):
        return UI_LANG[self.ui_lang].get(key, key)

    def _ev_unit(self):
        return "石/次" if self.ui_lang == "zh-TW" else " st/bm"

    def switch_ui_language(self, lang):
        self.ui_lang = lang
        self.settings.setValue("ui_language", lang)
        t = UI_LANG[lang]

        self.tabWidget.setTabText(0, t["tab_function"])
        self.tabWidget.setTabText(1, t["tab_help"])
        self.tabWidget.setTabText(2, t["tab_stats"])

        self.lblRefreshCountTitle.setText(t["label_refresh_count"])
        self.lblGoldTitle.setText(t["label_gold"])
        self.lblStoneTitle.setText(t["label_stone"])
        self.stopGroupBox.setTitle(t["group_stop"])
        self.radioCov.setText(t["radio_cov"])
        self.radioMys.setText(t["radio_mys"])
        self.radioStone.setText(t["radio_stone"])
        self.lblDebugTitle.setText(t["label_debug"])
        self.connGroup.setTitle(t["group_adb"])
        self.lblHostTitle.setText(t["label_host"])
        self.lblPortTitle.setText(t["label_port"])
        self.lblLangTitle.setText(t["label_lang"])
        self.lblUiLangTitle.setText(t["label_ui_lang"])
        self.btnStart.setText(t["btn_stop"] if self.running else t["btn_start"])
        self.btnTestConn.setText(t["btn_test"])
        self.btnReset.setText(t["btn_reset"])
        self.introTab.setHtml(t["help_html"])

        self.lblStatsSessionsTitle.setText(t["stats_sessions"])
        self.lblStatsRefreshesTitle.setText(t["stats_refreshes"])
        self.lblStatsStonesTitle.setText(t["stats_stones"])
        self.lblStatsGoldTitle.setText(t["stats_gold"])
        self.lblStatsCovenantTitle.setText(t["stats_covenant"])
        self.lblStatsMysticTitle.setText(t["stats_mystic"])
        self.lblStatsEvCovTitle.setText(t["stats_ev_cov"])
        self.lblStatsEvMysTitle.setText(t["stats_ev_mys"])

        self._refresh_stats_display()

    def setupUi(self, Main):
        Main.setObjectName("Main")
        Main.resize(640, 550)
        font = QtGui.QFont("微軟正黑體", 10)
        Main.setFont(font)

        self.settings = QSettings("epic7autoBookmark", "epic7autoBookmark")
        self.ui_lang = self.settings.value("ui_language", "zh-TW")

        self.layout = QtWidgets.QVBoxLayout(Main)
        self.tabWidget = QtWidgets.QTabWidget(Main)

        # ============ 功能分頁 ============
        self.functionTab = QtWidgets.QWidget()
        self.fLayout = QtWidgets.QHBoxLayout(self.functionTab)

        # -- 左欄 --
        leftLayout = QtWidgets.QVBoxLayout()

        self.resLayout = QtWidgets.QGridLayout()
        self.lblGoldTitle = QtWidgets.QLabel(self.L("label_gold"))
        self.resLayout.addWidget(self.lblGoldTitle, 0, 0)
        self.moneyEdit = QtWidgets.QLineEdit(
            self.settings.value("money", "987654321"))
        self.resLayout.addWidget(self.moneyEdit, 0, 1)
        self.lblStoneTitle = QtWidgets.QLabel(self.L("label_stone"))
        self.resLayout.addWidget(self.lblStoneTitle, 1, 0)
        self.stoneEdit = QtWidgets.QLineEdit(
            self.settings.value("stone", "5000"))
        self.resLayout.addWidget(self.stoneEdit, 1, 1)
        leftLayout.addLayout(self.resLayout)

        self.stopGroupBox = QtWidgets.QGroupBox(self.L("group_stop"))
        self.sLayout = QtWidgets.QVBoxLayout(self.stopGroupBox)
        self.radioCov = QtWidgets.QRadioButton(self.L("radio_cov"))
        self.radioCov.setChecked(True)
        self.inputCov = QtWidgets.QLineEdit(
            self.settings.value("cov_target", "50"))
        self.radioMys = QtWidgets.QRadioButton(self.L("radio_mys"))
        self.inputMys = QtWidgets.QLineEdit(
            self.settings.value("mys_target", "0"))
        self.radioStone = QtWidgets.QRadioButton(self.L("radio_stone"))
        self.inputStone = QtWidgets.QLineEdit(
            self.settings.value("stone_target", "0"))
        self.sLayout.addWidget(self.radioCov)
        self.sLayout.addWidget(self.inputCov)
        self.sLayout.addWidget(self.radioMys)
        self.sLayout.addWidget(self.inputMys)
        self.sLayout.addWidget(self.radioStone)
        self.sLayout.addWidget(self.inputStone)
        leftLayout.addWidget(self.stopGroupBox)

        refreshCountLayout = QtWidgets.QHBoxLayout()
        self.lblRefreshCountTitle = QtWidgets.QLabel(self.L("label_refresh_count"))
        self.lblRefreshCount = QtWidgets.QLabel("0")
        font_bold = QtGui.QFont()
        font_bold.setBold(True)
        font_bold.setPointSize(12)
        self.lblRefreshCount.setFont(font_bold)
        refreshCountLayout.addWidget(self.lblRefreshCountTitle)
        refreshCountLayout.addWidget(self.lblRefreshCount)
        refreshCountLayout.addStretch()
        leftLayout.addLayout(refreshCountLayout)

        self.logBox = QtWidgets.QTextBrowser()
        leftLayout.addWidget(self.logBox)

        self.btnStart = QtWidgets.QPushButton(self.L("btn_start"))
        self.btnStart.setMinimumHeight(40)
        self.btnStart.clicked.connect(self.toggleStart)
        leftLayout.addWidget(self.btnStart)

        self.fLayout.addLayout(leftLayout)

        # -- 右欄 --
        rightLayout = QtWidgets.QVBoxLayout()

        # UI 語言切換
        uiLangLayout = QtWidgets.QHBoxLayout()
        self.lblUiLangTitle = QtWidgets.QLabel(self.L("label_ui_lang"))
        uiLangLayout.addWidget(self.lblUiLangTitle)
        self.uiLangCombo = QtWidgets.QComboBox()
        self.uiLangCombo.addItems(["zh-TW", "en"])
        idx = self.uiLangCombo.findText(self.ui_lang)
        if idx >= 0:
            self.uiLangCombo.setCurrentIndex(idx)
        self.uiLangCombo.currentTextChanged.connect(self.switch_ui_language)
        uiLangLayout.addWidget(self.uiLangCombo)
        rightLayout.addLayout(uiLangLayout)

        self.connGroup = QtWidgets.QGroupBox(self.L("group_adb"))
        connLayout = QtWidgets.QGridLayout(self.connGroup)
        self.lblHostTitle = QtWidgets.QLabel(self.L("label_host"))
        connLayout.addWidget(self.lblHostTitle, 0, 0)
        self.addrEdit = QtWidgets.QLineEdit(
            self.settings.value("adb_host", "127.0.0.1"))
        connLayout.addWidget(self.addrEdit, 0, 1)
        self.lblPortTitle = QtWidgets.QLabel(self.L("label_port"))
        connLayout.addWidget(self.lblPortTitle, 1, 0)
        self.portEdit = QtWidgets.QLineEdit(
            self.settings.value("adb_port", "5555"))
        connLayout.addWidget(self.portEdit, 1, 1)
        self.btnTestConn = QtWidgets.QPushButton(self.L("btn_test"))
        self.btnTestConn.clicked.connect(self.test_adb_connection)
        connLayout.addWidget(self.btnTestConn, 2, 0, 1, 2)
        rightLayout.addWidget(self.connGroup)

        langLayout = QtWidgets.QHBoxLayout()
        self.lblLangTitle = QtWidgets.QLabel(self.L("label_lang"))
        langLayout.addWidget(self.lblLangTitle)
        self.langCombo = QtWidgets.QComboBox()
        self.langCombo.addItems(["zh-TW", "zh-CN", "en-US"])
        savedLang = self.settings.value("e7_language", "zh-TW")
        idx = self.langCombo.findText(savedLang)
        if idx >= 0:
            self.langCombo.setCurrentIndex(idx)
        langLayout.addWidget(self.langCombo)
        rightLayout.addLayout(langLayout)

        self.lblDebugTitle = QtWidgets.QLabel(self.L("label_debug"))
        rightLayout.addWidget(self.lblDebugTitle)
        self.debugBox = QtWidgets.QTextBrowser()
        rightLayout.addWidget(self.debugBox)

        self.fLayout.addLayout(rightLayout)

        self.tabWidget.addTab(self.functionTab, self.L("tab_function"))

        # ============ 說明分頁 ============
        self.introTab = QtWidgets.QTextBrowser()
        self.introTab.setHtml(self.L("help_html"))
        self.tabWidget.addTab(self.introTab, self.L("tab_help"))

        # ============ 統計分頁 ============
        self.statsTab = QtWidgets.QWidget()
        statsLayout = QtWidgets.QVBoxLayout(self.statsTab)

        statsGrid = QtWidgets.QGridLayout()
        self.lblStatsSessionsTitle = QtWidgets.QLabel(self.L("stats_sessions"))
        statsGrid.addWidget(self.lblStatsSessionsTitle, 0, 0)
        self.lblSessions = QtWidgets.QLabel("0")
        statsGrid.addWidget(self.lblSessions, 0, 1)
        self.lblStatsRefreshesTitle = QtWidgets.QLabel(self.L("stats_refreshes"))
        statsGrid.addWidget(self.lblStatsRefreshesTitle, 1, 0)
        self.lblRefreshes = QtWidgets.QLabel("0")
        statsGrid.addWidget(self.lblRefreshes, 1, 1)
        self.lblStatsStonesTitle = QtWidgets.QLabel(self.L("stats_stones"))
        statsGrid.addWidget(self.lblStatsStonesTitle, 2, 0)
        self.lblStones = QtWidgets.QLabel("0")
        statsGrid.addWidget(self.lblStones, 2, 1)
        self.lblStatsGoldTitle = QtWidgets.QLabel(self.L("stats_gold"))
        statsGrid.addWidget(self.lblStatsGoldTitle, 3, 0)
        self.lblGold = QtWidgets.QLabel("0")
        statsGrid.addWidget(self.lblGold, 3, 1)
        self.lblStatsCovenantTitle = QtWidgets.QLabel(self.L("stats_covenant"))
        statsGrid.addWidget(self.lblStatsCovenantTitle, 4, 0)
        self.lblCovenant = QtWidgets.QLabel("0")
        statsGrid.addWidget(self.lblCovenant, 4, 1)
        self.lblStatsMysticTitle = QtWidgets.QLabel(self.L("stats_mystic"))
        statsGrid.addWidget(self.lblStatsMysticTitle, 5, 0)
        self.lblMystic = QtWidgets.QLabel("0")
        statsGrid.addWidget(self.lblMystic, 5, 1)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        statsGrid.addWidget(sep, 6, 0, 1, 2)
        self.lblStatsEvCovTitle = QtWidgets.QLabel(self.L("stats_ev_cov"))
        statsGrid.addWidget(self.lblStatsEvCovTitle, 7, 0)
        self.lblEvCov = QtWidgets.QLabel("—")
        statsGrid.addWidget(self.lblEvCov, 7, 1)
        self.lblStatsEvMysTitle = QtWidgets.QLabel(self.L("stats_ev_mys"))
        statsGrid.addWidget(self.lblStatsEvMysTitle, 8, 0)
        self.lblEvMys = QtWidgets.QLabel("—")
        statsGrid.addWidget(self.lblEvMys, 8, 1)
        statsLayout.addLayout(statsGrid)

        statsLayout.addStretch()

        self.btnReset = QtWidgets.QPushButton(self.L("btn_reset"))
        self.btnReset.clicked.connect(self.resetStats)
        statsLayout.addWidget(self.btnReset)

        self.tabWidget.addTab(self.statsTab, self.L("tab_stats"))

        self.layout.addWidget(self.tabWidget)

        self._refresh_stats_display()

        # 初始化 Worker
        self.worker = worker()
        self.worker.isStart.connect(lambda: self.logBox.append(self.L("log_start")))
        self.worker.isFinish.connect(self.onFinish)
        self.worker.isError.connect(lambda e: self.logBox.append(f"❌ 錯誤: {e}"))
        self.worker.emitLog.connect(lambda t: self.logBox.append(t))
        self.worker.emitLog.connect(lambda t: self.debugBox.append(t))
        self.worker.emitDebug.connect(lambda t: self.debugBox.append(t))
        self.worker.emitMoney.connect(lambda v: self.moneyEdit.setText(v))
        self.worker.emitStone.connect(lambda v: self.stoneEdit.setText(v))
        self.worker.emitRefreshCount.connect(lambda v: self.lblRefreshCount.setText(v))

        self.running = False

    def test_adb_connection(self):
        host = self.addrEdit.text().strip()
        port = self.portEdit.text().strip()
        addr = f"{host}:{port}"
        try:
            adb.connect(addr, timeout=5)
            device = adb.device(serial=addr)
            img = device.screenshot()
            self.logBox.append(self.L("test_ok"))
            self.debugBox.append(self.L("test_ok"))

            from io import BytesIO
            buf = BytesIO()
            img.save(buf, format="PNG")
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            scaled = pixmap.scaled(
                480, 270,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )

            dlg = QtWidgets.QDialog()
            dlg.setWindowTitle(f"ADB Screenshot — {addr}")
            dlg.setWindowIcon(self.lblSessions.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))
            layout = QtWidgets.QVBoxLayout(dlg)
            lbl = QtWidgets.QLabel()
            lbl.setPixmap(scaled)
            layout.addWidget(lbl)
            dlg.exec()
        except Exception as e:
            self.logBox.append(f"{self.L('test_fail')}: {e}")

    def _save_settings(self):
        self.settings.setValue("adb_host", self.addrEdit.text())
        self.settings.setValue("adb_port", self.portEdit.text())
        self.settings.setValue("e7_language", self.langCombo.currentText())
        self.settings.setValue("money", self.moneyEdit.text())
        self.settings.setValue("stone", self.stoneEdit.text())
        self.settings.setValue("cov_target", self.inputCov.text())
        self.settings.setValue("mys_target", self.inputMys.text())
        self.settings.setValue("stone_target", self.inputStone.text())

    def toggleStart(self):
        if not self.running:
            self._save_settings()

            host = self.addrEdit.text().strip()
            port = self.portEdit.text().strip()
            lang = self.langCombo.currentText()

            mode = 1 if self.radioCov.isChecked() else (2 if self.radioMys.isChecked() else 3)
            num = int(self.inputCov.text()) if mode==1 else (int(self.inputMys.text()) if mode==2 else int(self.inputStone.text()))

            config = {
                "adb_addr": f"{host}:{port}",
                "e7_language": lang,
            }

            self.worker.setVariable(
                mode, num,
                int(self.moneyEdit.text()),
                int(self.stoneEdit.text()),
                config,
                self._load_cumulative()
            )
            self.worker.start()
            self.btnStart.setText(self.L("btn_stop"))
            self.running = True
        else:
            self.worker.terminate()
            self.onFinish(self.L("log_stop"))

    def _load_cumulative(self):
        return {
            "total_sessions": int(self.settings.value("total_sessions", 0)),
            "total_refreshes": int(self.settings.value("total_refreshes", 0)),
            "total_stones": int(self.settings.value("total_stones", 0)),
            "total_gold": int(self.settings.value("total_gold", 0)),
            "total_covenant": int(self.settings.value("total_covenant", 0)),
            "total_mystic": int(self.settings.value("total_mystic", 0)),
        }

    def _save_cumulative(self, d):
        for k, v in d.items():
            self.settings.setValue(k, v)

    def _refresh_stats_display(self):
        c = self._load_cumulative()
        self.lblSessions.setText(str(c["total_sessions"]))
        self.lblRefreshes.setText(f"{c['total_refreshes']:,}")
        self.lblStones.setText(f"{c['total_stones']:,}")
        self.lblGold.setText(f"{c['total_gold']:,}")
        self.lblCovenant.setText(str(c["total_covenant"]))
        self.lblMystic.setText(str(c["total_mystic"]))

        stones = c["total_stones"]
        cov = c["total_covenant"]
        mys = c["total_mystic"]
        unit = self._ev_unit()
        self.lblEvCov.setText(f"{stones / cov:.2f}{unit}" if cov > 0 else "—")
        self.lblEvMys.setText(f"{stones / mys:.2f}{unit}" if mys > 0 else "—")

    def resetStats(self):
        reply = QtWidgets.QMessageBox.question(
            None,
            self.L("confirm_reset_title"),
            self.L("confirm_reset_msg"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._save_cumulative({
                "total_sessions": 0,
                "total_refreshes": 0,
                "total_stones": 0,
                "total_gold": 0,
                "total_covenant": 0,
                "total_mystic": 0,
            })
            self._refresh_stats_display()
            self.logBox.append(self.L("log_reset"))

    def onFinish(self, msg):
        self.logBox.append("\n" + msg)

        cum = self._load_cumulative()
        cum["total_sessions"] += 1
        cum["total_refreshes"] += self.worker.refreshTime
        cum["total_stones"] += self.worker.refreshTime * 3
        cum["total_gold"] += self.worker.totalMoneySpent
        cum["total_covenant"] += self.worker.covenantFoundCount
        cum["total_mystic"] += self.worker.mysticFoundCount
        self._save_cumulative(cum)
        self._refresh_stats_display()

        self.btnStart.setText(self.L("btn_start"))
        self.running = False

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("epic7autoBookmark")
    app.setApplicationName("epic7autoBookmark")
    try:
        app.setWindowIcon(QtGui.QIcon(resource_path("main.ico")))
    except Exception:
        pass
    window = QtWidgets.QWidget()
    ui = Ui_Main()
    ui.setupUi(window)
    window.show()
    sys.exit(app.exec())