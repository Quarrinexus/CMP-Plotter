"""The window's language: English, or Simplified Chinese (Mandarin).

Only what Tk shows is translated: the controls, hints, messages and dialogs.
What matplotlib draws (titles, labels, legends, Measure's marks), what's
stored (settings, sessions, a line's settings, which are menu keys) and file
names stay English, as matplotlib has no Chinese font set up here and a
figure is usually for a paper. `tr` looks a whole English sentence up, with
{named} places for what changes, as word order differs between the two."""

LANGUAGES = {"en": "English", "zh": "简体中文"}

# The font Tk draws a language in, where the language needs its own: (family,
# size in pixels). Tk's X core fonts (Linux) otherwise take Chinese characters
# from Japanese and Korean fonts, which lack many simplified ones (they show
# as boxes); song ti has all of GB2312, and 16 px is one of its real sizes.
FONTS = {"zh": ("song ti", -16)}

language = "en"
missing = set()  # English texts looked up in Chinese that have no translation


def set_language(code):
    """Use `code`, a key of LANGUAGES; anything else is English."""
    global language
    language = code if code in LANGUAGES else "en"


def tr(text, **values):
    """`text` in the window's language, with `values` put in its {places}."""
    if language == "zh":
        if text in ZH:
            text = ZH[text]
        else:
            missing.add(text)
    return text.format(**values) if values else text


def shown(mapping, key):
    """A menu's text for `key`, from a {key: English text} menu dict."""
    return tr(mapping[key])


def key_of(mapping, text):
    """The key whose menu text, as shown, is `text`."""
    return next(k for k, v in mapping.items() if tr(v) == text)


def menu(mapping):
    """A menu dict's texts as shown, in order, for a Combobox's values."""
    return [tr(v) for v in mapping.values()]


# English -> Simplified Chinese. Keys are the exact English texts passed to tr.
ZH = {
    # The window and its sections
    "Files": "文件",
    "Data folder": "数据文件夹",
    "Output folder": "输出文件夹",
    "Choose data folder": "选择数据文件夹",
    "Choose output folder": "选择输出文件夹",
    "Browse...": "浏览…",
    "(not set)": "（未设置）",
    "Data format...": "数据格式…",
    "Session": "会话",
    "Open session...": "打开会话…",
    "Save session...": "保存会话…",
    "Open session": "打开会话",
    "Save session": "保存会话",
    "Dataset": "数据集",
    "Lines": "曲线",
    "X axis": "X 轴",
    "Y axis": "Y 轴",
    "Function": "函数",
    "e.g. 1/{name}; Enter applies": "例如 1/{name}；按回车应用",
    "Save as": "另存为",
    "Delete panel": "删除面板",
    "Layout": "布局",
    "Saving Options": "保存选项",
    "Save figure": "保存图像",
    "Process": "处理",
    "Splicing": "截取",
    "Derive": "派生",
    "Linking": "联动",
    "Measure": "测量",

    # Process
    "Smoothing": "平滑",
    "None": "无",
    "Moving average": "滑动平均",
    "Median": "中值",
    "Savitzky-Golay": "Savitzky-Golay",
    "Window": "窗口",
    "points": "点",
    "x units": "x 单位",
    "Order": "阶数",
    "Background": "背景",
    "Off": "关",
    "Show fit": "显示拟合",
    "Subtract": "扣除",
    "Degree": "次数",
    "Fit x": "拟合 x",
    "to": "至",
    "Pick": "选取",

    # Splicing
    "Keep ranges": "保留区间",
    "Remove ranges": "去除区间",
    "Add": "添加",
    "Delete": "删除",
    "x from {start}": "x 从 {start} 起",
    "x up to {end}": "x 到 {end} 为止",
    "x {start} to {end}": "x {start} 至 {end}",
    "in the plotted x; a blank end: no limit": "按绘图的 x；端点留空：不限",
    "click a range, then Enter changes it": "点击区间，再按回车修改",
    "cut before fits, smoothing and FFT": "在拟合、平滑和 FFT 之前截取",
    "on an FFT: cuts the spectrum, in F": "FFT 面板上：按 F 截取频谱",
    "'{text}' isn't a number.": "“{text}”不是数字。",
    "Type at least one end of the range.": "请至少输入区间的一端。",
    "Keeping the range; choose Remove ranges to cut it out instead.":
        "已保留该区间；若要去除它，请选择“去除区间”。",
    "Click a range in the list to delete it.": "请在列表中点击要删除的区间。",

    # Derive
    "FFT": "FFT",
    "FFT: this panel": "FFT：本面板",
    "FFT: of panel {n}": "FFT：面板 {n} 的",
    "FFT of {source}": "FFT，来自{source}",
    "first derivative": "一阶导数",
    "second derivative": "二阶导数",
    "Derivative": "导数",
    "Derivative: {kind}, this panel": "导数：{kind}，本面板",
    "Derivative: {kind} of panel {n}": "导数：面板 {n} 的{kind}",
    "{kind} of {source}": "{kind}，来自{source}",
    "First": "一阶",
    "Second": "二阶",
    "use 1/x on B for F in T": "对 B 使用 1/x，F 的单位为 T",
    "Hann": "Hann",
    "Padding": "补零",
    "F max": "F 上限",
    "blank: all": "留空：全部",
    "Back to data": "回到数据",
    "New panel": "新面板",
    "Existing panel...": "已有面板…",
    "This panel": "本面板",
    "Undo": "撤销",
    "back to its data": "回到其数据",
    "in place of its data": "替换其数据",
    "in its place": "替换当前",
    "points, odd": "点，奇数",
    "wider for less noise; 2nd needs more": "越宽噪声越小；二阶需要更宽",
    "Click This panel for its FFT instead.": "点击“本面板”改为显示其 FFT。",
    "Click This panel for its derivative instead.": "点击“本面板”改为显示其导数。",
    "Select {panel} to make its FFT.": "选择{panel}来生成其 FFT。",
    "Select {panel} to make its derivative.": "选择{panel}来生成其导数。",
    "panel {n}": "面板 {n}",
    "a data panel": "一个数据面板",
    "panel {n}, linked to it (see Linking).": "面板 {n}，与之联动（见“联动”）。",
    "its own lines; it no longer follows a panel.": "其自身的曲线；不再跟随任何面板。",
    "this panel's lines, drawn in their place; Undo brings them back.":
        "本面板的曲线，已原地替换；“撤销”可恢复。",
    "This panel is already an FFT; select its data panel to make its {kind}.":
        "本面板已是 FFT；请选择其数据面板来生成{kind}。",
    "This panel is already a {current}; select its data panel to make its {kind}.":
        "本面板已是{current}；请选择其数据面板来生成{kind}。",
    "The layout is full; put it in an existing panel.": "布局已满；请放入已有面板。",
    "There's only one panel; put it in a new panel.": "只有一个面板；请放入新面板。",
    "Click the panel to put the {kind} in; Esc cancels.": "点击要放入{kind}的面板；按 Esc 取消。",
    "Click a different panel for the {kind}.": "请为{kind}点击另一个面板。",
    "Replace panel?": "替换面板？",
    "Replace panel {target}'s lines with the {kind} of panel {source}?":
        "用面板 {source} 的{kind}替换面板 {target} 的曲线？",
    "Replace panel {target}'s lines with the {kind} of panel {source}, and the panels derived from it will stop following it?":
        "用面板 {source} 的{kind}替换面板 {target} 的曲线，由它导出的面板将不再跟随它？",

    # Linking
    "Link...": "联动…",
    "Unlink": "取消联动",
    "Freeze": "冻结",
    "Unfreeze": "解冻",
    "Sync": "同步",
    "X function": "X 函数",
    "Y function": "Y 函数",
    "Colour": "颜色",
    "Line style": "线型",
    "Linked to panel {numbers}": "已与面板 {numbers} 联动",
    "Linked to panels {numbers}": "已与面板 {numbers} 联动",
    "Not linked": "未联动",
    "Panel {n}": "面板 {n}",
    "Panel {n} (frozen)": "面板 {n}（已冻结）",
    "the link between panels {a} and {b}": "面板 {a} 与 {b} 之间的联动",
    "There's only one panel; choose a bigger Layout first.": "只有一个面板；请先选择更大的布局。",
    "Click the panel to link to; Esc cancels.": "点击要联动的面板；按 Esc 取消。",
    "Click a different panel to link to.": "请点击另一个面板进行联动。",
    "Those panels are already linked.": "这些面板已经联动。",
    "Link panels?": "联动面板？",
    "Panel {target} has {count} line, so {extra} of panel {cell}'s (and those linked to it) will be removed. Link anyway?":
        "面板 {target} 有 {count} 条曲线，因此面板 {cell}（及与其联动的面板）将删除 {extra} 条。仍要联动吗？",
    "Panel {target} has {count} lines, so {extra} of panel {cell}'s (and those linked to it) will be removed. Link anyway?":
        "面板 {target} 有 {count} 条曲线，因此面板 {cell}（及与其联动的面板）将删除 {extra} 条。仍要联动吗？",

    # Measure
    "Region": "区域",
    "Set": "设定",
    "Clear": "清除",
    "Max": "最大值",
    "Min": "最小值",
    "Peak to peak": "峰峰值",
    "Mean": "平均值",
    "Points": "点数",
    "Line {n}": "曲线 {n}",
    "Plot the selected line to measure it.": "请先绘制所选曲线再测量。",
    " (no points in the region)": "（区域内没有数据点）",
    "Mark the max and min on the plot": "在图上标出最大值和最小值",
    "Mark the peaks on the plot": "在图上标出峰",
    "Read points": "读取点",
    "Clear points": "清除点",
    "Peaks": "峰",
    "Up to": "最多",
    "over": "高于",
    "% of the top": "% 最高峰",
    "Marks in saved figures": "保存的图像中保留标记",
    "Copy": "复制",
    "Export CSV": "导出 CSV",
    "Export measurements": "导出测量结果",
    "Plot the selected line first, then read points off it.": "请先绘制所选曲线，再从中读取点。",
    "Click near the line to read a point; Esc stops.": "在曲线附近点击以读取点；按 Esc 停止。",
    "Nothing measured to copy.": "没有可复制的测量结果。",
    "Copied the measurements.": "已复制测量结果。",
    "Nothing measured to export.": "没有可导出的测量结果。",
    "Couldn't export: {err}": "无法导出：{err}",
    "Exported {name}": "已导出 {name}",

    # Picking ranges
    "Pick the fit range on the data panel, not its {kind}.": "请在数据面板上选取拟合区间，而不是在其{kind}上。",
    "Pick the cut range on the data panel, not its {kind}.": "请在数据面板上选取截取区间，而不是在其{kind}上。",
    "Plot the line first, then pick its fit range.": "请先绘制曲线，再选取拟合区间。",
    "Plot the line first, then pick its cut range.": "请先绘制曲线，再选取截取区间。",
    "Plot the line first, then pick its measuring range.": "请先绘制曲线，再选取测量区间。",
    "Drag across the plot to set the fit range; Esc cancels.": "在图上拖动以设定拟合区间；按 Esc 取消。",
    "Drag across the plot to set the cut range; Esc cancels.": "在图上拖动以设定截取区间；按 Esc 取消。",
    "Drag across the plot to set the measuring range; Esc cancels.": "在图上拖动以设定测量区间；按 Esc 取消。",
    "Turn off the toolbar's zoom or pan first.": "请先关闭工具栏的缩放或平移。",
    "Range set; choose Show fit or Subtract to use it.": "区间已设定；选择“显示拟合”或“扣除”以使用它。",

    # Messages
    "Could not load dataset: {error}": "无法加载数据集：{error}",
    "Couldn't remember the folder: {err}": "无法记住该文件夹：{err}",
    "Couldn't remember that: {err}": "无法记住该设置：{err}",
    "Couldn't remember them: {err}": "无法记住这些设置：{err}",
    "No data files in the data folder.": "数据文件夹中没有数据文件。",
    "Choose a data folder first.": "请先选择数据文件夹。",
    "Couldn't save the format: {err}": "无法保存格式：{err}",
    "Couldn't read {name}: {err}": "无法读取 {name}：{err}",
    "Deleted panel {n}; Ctrl+Z brings it back.": "已删除面板 {n}；按 Ctrl+Z 可恢复。",
    "Undone. (One step only.)": "已撤销。（仅一步。）",
    "Nothing to undo.": "没有可撤销的操作。",
    "Couldn't save the session: {err}": "无法保存会话：{err}",
    "Saved session {name}": "已保存会话 {name}",
    "Couldn't open {name}: {err}": "无法打开 {name}：{err}",
    "Opened session {name}": "已打开会话 {name}",
    "it isn't a GOOSE Plotter session": "它不是 GOOSE Plotter 会话",
    "it's from a newer version of the plotter": "它来自更新版本的绘图程序",
    "; couldn't remember its data folder: {err}": "；无法记住其数据文件夹：{err}",
    "; its data folder {folder} isn't there, so using this one": "；其数据文件夹 {folder} 不存在，因此使用当前文件夹",
    "Nothing plotted to save.": "没有可保存的图。",
    "Choose an output folder to save into.": "请选择保存用的输出文件夹。",
    "Can't use the output folder: {err}": "无法使用输出文件夹：{err}",
    "Not saved: the file is already there.": "未保存：文件已存在。",
    "Saved {path}": "已保存 {path}",
    "That's too big: keep each side under {n} pixels.": "尺寸过大：每边请保持在 {n} 像素以内。",
    "Can't draw that title: {why}": "无法绘制该标题：{why}",
    "Can't draw that x label: {why}": "无法绘制该 x 标签：{why}",
    "Can't draw that y label: {why}": "无法绘制该 y 标签：{why}",
    "Can't draw that name: {why}": "无法绘制该名称：{why}",
    "The x range needs two different ends.": "x 区间需要两个不同的端点。",
    "The y range needs two different ends.": "y 区间需要两个不同的端点。",

    # Axes editor
    "Axes of panel {n}": "面板 {n} 的坐标轴",
    "Range": "范围",
    "x from": "x 从",
    "y from": "y 从",
    "Use current view": "使用当前视图",
    "blank: automatic": "留空：自动",
    "Text": "文字",
    "Title": "标题",
    "x label": "x 标签",
    "y label": "y 标签",
    "Auto": "自动",
    "clear for none, Auto for the automatic text; $B$ for maths": "清空则不显示，“自动”为自动文字；$B$ 表示公式",
    "Legend": "图例",
    "Top right": "右上",
    "Top left": "左上",
    "Bottom left": "左下",
    "Bottom right": "右下",
    "Outside right": "右侧外部",
    "Grid": "网格",
    "show": "显示",
    "axis": "轴",
    "style": "样式",
    "Major": "主",
    "Major + minor": "主 + 次",
    "Both": "两者",
    "x only": "仅 x",
    "y only": "仅 y",
    "Solid": "实线",
    "Dashed": "虚线",
    "Dotted": "点线",
    "Ticks": "刻度",
    "Point inward (all panels)": "朝内（所有面板）",
    "Enter in a box applies": "在输入框中按回车应用",
    "Close": "关闭",

    # Line editor
    "Line": "线条",
    "Automatic": "自动",
    "Dash-dot": "点划线",
    "Width": "宽度",
    " (auto)": "（自动）",
    "Marker": "标记",
    "Dots": "点",
    "Circles": "圆",
    "Squares": "方块",
    "Triangles": "三角",
    "Crosses": "叉",
    "Size": "大小",
    "Name in the legend": "图例中的名称",
    "Enter applies; clear it for none, Auto for the automatic one": "按回车应用；清空则不显示，“自动”为自动名称",

    # Saving options and the overwrite question
    "Save options": "保存选项",
    "As on screen": "与屏幕相同",
    "Custom": "自定义",
    "Height": "高度",
    "Resolution": "分辨率",
    "DPI": "DPI",
    "Transparent": "透明",
    "Enter in a box applies; kept for every figure": "在输入框中按回车应用；对所有图像有效",
    "{w} x {h} pixels": "{w} x {h} 像素",
    "Width and height need to be numbers.": "宽度和高度必须是数字。",
    "DPI needs to be a number.": "DPI 必须是数字。",
    "Width and height need to be more than 0.": "宽度和高度必须大于 0。",
    "DPI needs to be from 10 to 2400.": "DPI 必须在 10 到 2400 之间。",
    "Replace file?": "替换文件？",
    "{name} already exists in {folder}.": "{folder} 中已有 {name}。",
    "Replace it with this figure?": "用这张图像替换它吗？",
    "Don't ask me again": "不再询问",
    "Cancel": "取消",
    "Replace": "替换",

    # Data format
    "Data format - {name}": "数据格式 - {name}",
    "How the files in this data folder are laid out.": "此数据文件夹中文件的排布方式。",
    "Start of {name} (column names orange, first data line blue):": "{name} 的开头（列名为橙色，第一行数据为蓝色）：",
    "Delimiter": "分隔符",
    "Tab": "制表符",
    "Comma": "逗号",
    "Semicolon": "分号",
    "Spaces": "空格",
    "Other": "其他",
    "Column names on line (0: none)": "列名所在行（0：无）",
    "Data starts on line": "数据起始行",
    "Use automatic detection": "使用自动检测",
    "Save for this folder": "为此文件夹保存",
    "type the delimiter in the box beside Other": "请在“其他”旁的输入框中输入分隔符",
    "line numbers must be whole numbers": "行号必须是整数",
    "Can't read the file this way: {message}": "无法按此方式读取文件：{message}",
    "{columns} column, {rows} rows": "{columns} 列，{rows} 行",
    "{columns} columns, {rows} rows": "{columns} 列，{rows} 行",
}
