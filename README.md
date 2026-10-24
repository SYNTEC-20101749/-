# 发票管理系统

## v1.0.16（2026-10-24）

- 未分析发票时也可直接登记私车公用行程并导出 Excel；确认前选择保存文件夹。
- 自动记忆上次成功使用的私车 Excel 保存文件夹；取消选择不生成文件，也不影响已保存位置。
- Excel 确认和汇总文件更新在后台执行，导出失败可修正后重试。
- 发布包及源码快照见 [GitHub Releases](https://github.com/SYNTEC-20101749/-/releases/tag/v1.0.16)。

## v1.0.15（2026-10-23）

- 新增私车公用行程登记：日期与时间选择、使用者及车牌记忆、里程差与1.5元/公里补贴自动计算。
- 私车补贴和过路费只同步至“按日期汇总”中日期完全相同的行；同日多条记录累加，不自动新增日期。对应日期过路费以私车表为准，避免重复计入通行费发票；停车费仅导入私车Excel。
- 点击“确认补贴/出租车”后更新汇总PDF，并在勾选私车公用且有有效明细时按财务模板导出Excel。模板原件不被修改；每张表最多8条，超出时自动增加工作表。
- 一键打印可将当前已确认的私车Excel按A5横向转换并打印一份；修改未重新确认、取消勾选或文件缺失时不会打印旧Excel。该功能需要本机安装Microsoft Excel；“只打印汇总清单”不打印私车Excel。
- 私车公用表格及编辑器字号与按日期汇总表一致；确认按钮不再由Enter/回车触发。软件启动时默认最大化。
- 关于页面后台检查GitHub最新正式版本，按数字比较版本；更新时提供版本提示和下载页入口，不自动下载或安装。网络错误不阻塞界面，兼容Python 3.12 TLS环境。
- 本次还修正未匹配日期私车费用误入汇总的问题。未匹配的私车明细仍完整保留在Excel中，但不会进入上方汇总、PDF或归档总计。

## v1.0.14（2026-10-23）

- 生成的出差清单按已配对网约车行程单的逐笔日期与金额统计，同一天多笔行程自动累加。
- 例如 22.90 元的行程单，8 月 31 日 12.60 元、9 月 4 日 10.30 元，分别计入对应日期。
- 高铁等其他交通费用累加规则不变；发票明细、界面原有汇总、重命名、配对和 Excel 归档不变。
- 行程明细无法完整解析或合计与发票、行程单总额不一致时，保留原金额分配。
- 按 SYNTEC 域控规范从纯英文路径构建，采用目录模式、无控制台、禁用 UPX、中性语言版本资源。

当前仓库已移除早期的 Chrome 扩展部分，保留两条仍在使用的本地能力：

- python_recognizer：发票识别与整理流程
- invoice_desktop：基于 PyQt5 的桌面整理工具

当前版本能力：

- 输入单个 PDF 文件
- 优先提取 PDF 文本层
- 文本层不足时自动走本地 OCR 兜底
- 基于规则识别发票号、销售方、日期、金额、税额、价税合计/票价
- 扫描目录并自动配对网约车发票与行程单
- 扫描目录并输出汇总、按日期金额表、重命名方案和打印份数
- 提供一个 Qt 桌面界面，按“分析汇总并重命名 -> 打印”处理
- 输出结构化 JSON

## 安装依赖

```bash
pip install -r requirements-python.txt
```

## Python 识别原型

python_recognizer 的目标是把“发票类型、金额、税额、价税合计、日期、销售方”这些字段识别能力独立出来，便于单独验证准确率。

### Python 原型使用方式

1. 安装依赖

```bash
pip install -r requirements-python.txt
```

2. 运行识别

```bash
python -m python_recognizer.cli 你的发票.pdf
```

如果你不想手动输入路径，也可以直接这样运行，程序会弹出 PDF 选择窗口：

```bash
python -m python_recognizer.cli
```

如果你只想测试 PDF 文本层，不启用 OCR：

```bash
python -m python_recognizer.cli 你的发票.pdf --no-ocr --pretty
```

如果你要批量扫描一个目录，并自动配对网约车发票和行程单：

```bash
python -m python_recognizer.cli --pair-dir "E:\发票目录" --pretty
```

如果你不想手动输入目录路径，也可以直接这样运行，程序会弹出文件夹选择窗口：

```bash
python -m python_recognizer.cli --pair-dir --pretty
```

如果你要跑一条更完整的整理流程，输出汇总、按日期金额表、重命名建议和打印份数：

```bash
python -m python_recognizer.cli --organize-dir "E:\发票目录" --pretty
```

不想手动输入目录路径，也可以直接这样运行：

```bash
python -m python_recognizer.cli --organize-dir --pretty
```

如果你希望程序真的创建当天目录，并把重命名后的文件复制进去：

```bash
python -m python_recognizer.cli --organize-dir --apply-organize --pretty
```

### 桌面版 MVP

当前仓库新增了一个最小桌面版入口，位置在 invoice_desktop。

运行方式：

```bash
python -m invoice_desktop.main
```

桌面版当前能力：

- 选择待整理发票目录
- 执行分析汇总时同步重命名，把文件复制到当天日期目录
- 手动填写出差在途与出差补贴，其中出差补贴会计入汇总总计
- 展示按日期汇总表和发票明细，确认后可直接打印
- 自动生成打印用的汇总清单 PDF，包含日期汇总表和手动字段
- 一键打印整理后的 PDF，默认走 Windows 默认打印机和 A5 纸张
- 打开输出目录

这一版重点是把整理工作流拆顺，让确认汇总、重命名、打印三个动作分开执行。

3. 输出示例

```json
{
	"source_file": "sample.pdf",
	"text_source": "ocr",
	"ocr_used": true,
	"number": "123456789012",
	"vendor": "某某有限公司",
	"amount": 100.0,
	"tax_amount": 13.0,
	"total_amount": 113.0,
	"issue_date": "2026-06-12",
	"category": "办公",
	"text_length": 1240,
	"notes": "...",
	"matched_rules": {
		"total_amount": "价税合计直接命中",
		"amount": "金额直接命中",
		"tax_amount": "税额直接命中",
		"train_fare": "未命中"
	}
}
```

### 当前边界

- 当前 OCR 兜底基于 RapidOCR，本地可跑，适合先验证识别流程。
- 扫描件或复杂票据后续仍可继续升级到 PaddleOCR 或云端票据识别。
- 网约车配对当前优先依赖文件名中的“编号-金额-发票/行程单”规律，再用金额和日期做校验。
- 整理汇总当前默认网约车行程单不计入费用总额，避免和网约车发票重复统计。
- 整理模式当前会把建议输出目录设为“原目录/当天日期”，例如 `20260612/发票号码-总费用.pdf`。
- 如果当天目录已存在，整理模式会自动生成新的目录名，例如 `20260612-1`、`20260612-2`，避免覆盖上一次结果。
- 不带 `--apply-organize` 时只输出方案，不会真的创建目录或复制文件。
- 这一版适合先验证字段识别规则，不适合直接拿来做最终产品。

### 整理结果说明

`--organize-dir` 会输出三部分：

- `output_directory`: 建议放置重命名后文件的目标目录
- `applied`: 是否已经实际创建目录并复制文件
- `summary`: 汇总结果，包含交通费、过路费、住宿的 amount/tax/total，以及按日期聚合的 `daily_breakdown`
- `ride_hailing_pairs`: 网约车发票与行程单配对结果
- `records`: 每个 PDF 的识别结果、建议新文件名、打印份数、待复核提示

当前打印规则：

- 火车票：2 份
- 住宿票：2 份
- 其它：1 份

执行整理后会在当天输出目录里额外生成：

- `汇总清单.pdf`，包含按日期汇总表、出差在途、出差补贴

桌面版点击打印时：

- 先打印 1 张 `汇总清单.pdf`
- 使用当前 Windows 默认打印机
- 按记录中的 `print_copies` 份数打印
- 默认使用 A5 纸张
- 打印对象为整理后输出目录中的 PDF

### 在 VS Code 里怎么验证

这不是点某个 Python 文件直接看结果的模式，最直接的方式是运行任务：

1. 打开命令面板，执行 Run Task
2. 选择 Run Python OCR Prototype
3. 输入要识别的 PDF 绝对路径
4. 在终端里看 JSON 输出

如果你更习惯手动运行，也可以直接在终端执行上面的 python -m 命令；不带路径时会弹出文件选择框。

## 后续建议

如果你要继续做成正式产品，建议优先补这三块：

1. 接入 Google Cloud Vision API 或 Document AI 做 OCR。
2. 增加发票图片/PDF 文件上传和文件内容缓存。
3. 增加登录与云端同步，例如 Firebase 或你自己的后端。

## 使用统计后台（v1.0.12）

项目包含可选的内部使用统计后台，按 Windows 登录工号汇总使用次数，并显示电脑名、软件版本、最近使用时间、启动/分析/打印次数和最近操作记录。客户端不会上传发票、金额、文件路径、QQ 邮箱账号或授权码。

### 启动后台

在部署统计后台的受控内网服务器上安装 [usage_dashboard/requirements.txt](usage_dashboard/requirements.txt) 中的依赖；设置环境变量 `INVOICE_USAGE_API_KEY` 和 `INVOICE_USAGE_ADMIN_PASSWORD` 后，运行 [usage_dashboard/start_dashboard.ps1](usage_dashboard/start_dashboard.ps1)。默认监听 8080 端口，管理员以用户名 `admin` 和环境变量设置的密码访问网页首页。

建议仅在公司内网或经 HTTPS 反向代理后开放，并限制管理员访问来源。

### 启用客户端上报

统计后台地址由软件维护者固定写入客户端；终端用户无需通过 [ui_config.txt](ui_config.txt) 配置。客户端每次启动会自动发送一条启动统计记录；统计请求在后台线程中发送，超时、断网或服务异常均不会影响本地功能。
