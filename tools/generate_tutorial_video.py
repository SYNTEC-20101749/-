from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from typing import Iterable
import wave
import audioop

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "发票管理系统操作教学视频-v1.0.7.mp4"
SILENT_OUTPUT_PATH = ROOT / "docs" / "发票管理系统操作教学视频-v1.0.7-无声.mp4"
WIDTH, HEIGHT, FPS = 1280, 720, 30
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
BACKGROUND = "#F4EFE7"
NAVY = "#17324D"
BLUE = "#2F6F98"
ORANGE = "#B86B35"
GREEN = "#2F7D6D"
MUTED = "#6B6257"
CARD = "#FFFAF3"
BORDER = "#D8CDBD"
NARRATION_SEGMENTS = [
    "欢迎观看新代发票管理系统一点零点七操作教学。",
    "先将本次出差的 PDF 发票和行程单放在同一个文件夹，保留原始文件。",
    "点击选择文件夹，再点击分析汇总。系统会识别、配对、重命名，并生成 NewName 输出目录。",
    "请核对日期、类别、金额和发票号码。红色文字表示需要打开原始票据人工确认。",
    "需要邮箱抓取时，填写 QQ 邮箱、IMAP 授权码和日期。系统会先检查 VS Code；初始化按钮可清除保存的信息。",
    "高速票使用票面发票号码，不使用发票代码。配对成功的高速和网约车行程单，使用对应发票号码命名。",
    "最后生成 Excel 汇总清单。确认无误后，可以打印、打开输出目录或上传公共盘。",
    "报销前请以原始票据为准，完成最终复核。",
]


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    index = 1 if bold else 0
    return ImageFont.truetype(str(FONT_PATH), size=size, index=index)


def draw_rounded_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str = BORDER) -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=2)


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], *, max_width: int, text_font, fill: str, line_spacing: int = 12) -> int:
    x, y = xy
    current = ""
    lines: list[str] = []
    for char in text:
        candidate = current + char
        if draw.textlength(candidate, font=text_font) > max_width and current:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    for line in lines:
        draw.text((x, y), line, font=text_font, fill=fill)
        y += text_font.size + line_spacing
    return y


def base_canvas(step: str, title: str, subtitle: str) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 86), fill=NAVY)
    draw.text((54, 24), "SYNTEC  发票管理系统｜操作教学", font=font(29, bold=True), fill="white")
    draw.text((1045, 29), step, font=font(22), fill="#D8E8F3")
    draw.text((64, 124), title, font=font(48, bold=True), fill=NAVY)
    draw.text((67, 190), subtitle, font=font(24), fill=MUTED)
    return image


def draw_sidebar(draw: ImageDraw.ImageDraw, active: int) -> None:
    items = ["准备文件", "分析汇总", "核对明细", "邮箱抓取", "打印归档"]
    for index, item in enumerate(items):
        y = 275 + index * 62
        selected = index == active
        draw.rounded_rectangle((68, y, 290, y + 46), radius=12, fill=BLUE if selected else "#E9E0D4")
        draw.text((92, y + 10), f"{index + 1}. {item}", font=font(20, bold=selected), fill="white" if selected else NAVY)


def draw_fake_app(image: Image.Image, active: int, body_title: str, rows: Iterable[tuple[str, str, str]]) -> None:
    draw = ImageDraw.Draw(image)
    draw_rounded_box(draw, (48, 250, 1232, 655), "#FFFFFF")
    draw_sidebar(draw, active)
    draw.text((340, 280), body_title, font=font(29, bold=True), fill=NAVY)
    draw.rounded_rectangle((340, 332, 1110, 385), radius=12, fill="#EFE3D2")
    for position, heading in enumerate(["项目", "操作/结果", "说明"]):
        draw.text((365 + (0, 250, 530)[position], 347), heading, font=font(19, bold=True), fill="#5F4832")
    for index, row in enumerate(rows):
        top = 394 + index * 66
        draw.line((340, top, 1110, top), fill="#EADFD1", width=2)
        draw.text((365, top + 17), row[0], font=font(19, bold=True), fill=NAVY)
        draw.text((615, top + 17), row[1], font=font(19), fill=ORANGE)
        draw.text((895, top + 17), row[2], font=font(18), fill=MUTED)


def title_slide() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((94, 94, 1186, 620), radius=38, fill="#FFFDF9")
    draw.text((160, 180), "SYNTEC", font=font(34, bold=True), fill=ORANGE)
    draw.text((160, 245), "发票管理系统", font=font(62, bold=True), fill=NAVY)
    draw.text((163, 334), "v1.0.7 操作教学视频", font=font(34, bold=True), fill=BLUE)
    draw.text((165, 411), "发票整理 · 邮箱抓取 · 汇总打印 · Excel 归档", font=font(26), fill=MUTED)
    draw.text((165, 493), "建议按本视频顺序完成每次报销资料处理。", font=font(23), fill=GREEN)
    return image


def prepare_slide() -> Image.Image:
    image = base_canvas("01 / 05", "第一步：准备待处理文件", "将同一趟出差的 PDF 发票与配套行程单放在同一个文件夹。")
    draw_fake_app(image, 0, "开始前检查", [
        ("原始票据", "PDF 文件", "请保留原文件"),
        ("网约车", "发票 + 行程单", "放在同一目录"),
        ("目录内容", "仅本次报销资料", "避免混入旧汇总"),
        ("扫描件", "允许 OCR 识别", "处理后人工复核"),
    ])
    return image


def analysis_slide() -> Image.Image:
    image = base_canvas("02 / 05", "第二步：选择文件夹并分析汇总", "点击“选择文件夹”后，点击“分析汇总”；系统会创建“原目录-NewName”输出目录。")
    draw_fake_app(image, 1, "操作步骤", [
        ("选择文件夹", "选择本次发票目录", "目录切换后需重新分析"),
        ("分析汇总", "识别 / 配对 / 重命名", "请等待处理完成"),
        ("自动结果", "汇总清单.pdf", "写入输出目录"),
        ("输出副本", "不修改原始 PDF", "便于安全留存"),
    ])
    return image


def review_slide() -> Image.Image:
    image = base_canvas("03 / 05", "第三步：核对明细与按日期汇总", "重点检查日期、类别、金额、税额、发票号码和“提示”栏。")
    draw_fake_app(image, 2, "发票明细复核", [
        ("日期", "实际发生日期", "乘车 / 通行 / 入住日期"),
        ("发票号码", "票面号码", "不是发票代码"),
        ("红色文字", "需要人工复核", "打开原 PDF 确认"),
        ("填写补贴/出租车", "补录人工费用", "完成后点击确认"),
    ])
    return image


def mail_slide() -> Image.Image:
    image = base_canvas("04 / 05", "第四步：QQ 邮箱发票抓取", "适用于从 QQ 邮箱按邮件收件日期下载发票附件。")
    draw_fake_app(image, 3, "邮箱抓取流程", [
        ("前置检查", "检测 Visual Studio Code", "未安装时停止抓取"),
        ("登录信息", "QQ 邮箱 + IMAP 授权码", "不要输入 QQ 登录密码"),
        ("日期范围", "起始日 至 结束日", "左右端日期均包含"),
        ("初始化", "清除保存的账号/授权码", "切换账号时使用"),
    ])
    return image


def naming_slide() -> Image.Image:
    image = base_canvas("04 / 05", "邮箱抓取后的命名规则", "系统会过滤结账单等无关附件，并统一使用分析汇总相同的命名规则。")
    draw = ImageDraw.Draw(image)
    draw_rounded_box(draw, (70, 270, 1210, 590), CARD)
    entries = [
        ("高速通行票", "18759981-106.00-高速通行票.pdf", "使用票面“发票号码”，不使用发票代码"),
        ("高速行程单", "18759981-106.00行程单.pdf", "与对应发票成功配对后命名"),
        ("网约车行程单", "发票号码-金额行程单.pdf", "优先按编号、同邮件或唯一金额配对"),
    ]
    for index, (kind, filename, note) in enumerate(entries):
        top = 304 + index * 86
        draw.text((105, top), kind, font=font(23, bold=True), fill=BLUE)
        draw.text((340, top), filename, font=font(22, bold=True), fill=ORANGE)
        draw.text((340, top + 34), note, font=font(18), fill=MUTED)
    return image


def finish_slide() -> Image.Image:
    image = base_canvas("05 / 05", "第五步：生成、打印与归档", "确认明细无误后，即可生成归档、打印或上传整理后的 PDF。")
    draw_fake_app(image, 4, "完成本次报销资料", [
        ("生成汇总清单并打开", "发票打印汇总档案.xlsx", "用于归档与复核"),
        ("一键打印", "汇总清单 + 票据", "先确认打印机设定"),
        ("打开输出目录", "查看重命名 PDF", "保留原始文件不受影响"),
        ("上传公共盘", "选择目标文件夹", "不上传汇总 PDF"),
    ])
    return image


def closing_slide() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    draw.text((130, 170), "操作完成", font=font(62, bold=True), fill="white")
    draw.text((134, 278), "请在报销前以原始票据为准，完成最终人工复核。", font=font(28), fill="#D8E8F3")
    draw.rounded_rectangle((130, 390, 750, 500), radius=18, fill=ORANGE)
    draw.text((170, 420), "发票管理系统  v1.0.7", font=font(31, bold=True), fill="white")
    draw.text((134, 570), "SYNTEC", font=font(23, bold=True), fill="#F4B400")
    return image


def frames_for_slide(image: Image.Image, seconds: float, *, transition: bool = True):
    frame_count = int(seconds * FPS)
    source = np.asarray(image)
    for frame_index in range(frame_count):
        if transition and frame_index < int(0.35 * FPS):
            alpha = (frame_index + 1) / (0.35 * FPS)
            frame = (source * alpha + np.full_like(source, 244) * (1 - alpha)).astype(np.uint8)
        else:
            frame = source
        yield cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)


def synthesize_narration_segment(text: str, destination: Path) -> None:
    """调用 Windows SAPI 生成中文旁白，优先使用系统中文语音。"""
    text_path = destination.with_suffix(".txt")
    text_path.write_text(text, encoding="utf-8-sig")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$chineseVoice = $speaker.GetInstalledVoices() | "
        "Where-Object { $_.VoiceInfo.Culture.Name -eq 'zh-CN' } | Select-Object -First 1; "
        "if ($chineseVoice) { $speaker.SelectVoice($chineseVoice.VoiceInfo.Name) }; "
        "$speaker.Rate = 7; "
        "$speaker.SetOutputToWaveFile($env:INVOICE_NARRATION_WAV); "
        "$speaker.Speak((Get-Content -LiteralPath $env:INVOICE_NARRATION_TEXT -Raw -Encoding UTF8)); "
        "$speaker.Dispose()"
    )
    environment = os.environ.copy()
    environment["INVOICE_NARRATION_TEXT"] = str(text_path)
    environment["INVOICE_NARRATION_WAV"] = str(destination)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        env=environment,
    )


def append_silence(output: wave.Wave_write, frame_count: int) -> None:
    output.writeframes(b"\x00" * frame_count * 2)


def normalize_wave_audio(segment: wave.Wave_read, target_rate: int) -> bytes:
    """将 SAPI 输出统一为 16 位单声道固定采样率，避免语音声音参数差异。"""
    audio = segment.readframes(segment.getnframes())
    channels = segment.getnchannels()
    sample_width = segment.getsampwidth()
    sample_rate = segment.getframerate()
    if sample_width != 2:
        audio = audioop.lin2lin(audio, sample_width, 2)
    if channels == 2:
        audio = audioop.tomono(audio, 2, 0.5, 0.5)
    elif channels != 1:
        raise RuntimeError("不支持的旁白音频声道数。")
    if sample_rate != target_rate:
        audio, _ = audioop.ratecv(audio, 2, 1, sample_rate, target_rate, None)
    return audio


def build_narration_track(destination: Path) -> None:
    """按视频页面顺序合并旁白段落，并在段落间留出短暂停顿。"""
    with tempfile.TemporaryDirectory(prefix="invoice_tutorial_narration_") as temporary_directory:
        temporary_path = Path(temporary_directory)
        segment_paths: list[Path] = []
        for index, text in enumerate(NARRATION_SEGMENTS, start=1):
            segment_path = temporary_path / f"narration_{index}.wav"
            synthesize_narration_segment(text, segment_path)
            segment_paths.append(segment_path)

        target_rate = 22050

        with wave.open(str(destination), "wb") as output:
            output.setparams((1, 2, target_rate, 0, "NONE", "not compressed"))
            for index, segment_path in enumerate(segment_paths):
                with wave.open(str(segment_path), "rb") as segment:
                    output.writeframes(normalize_wave_audio(segment, target_rate))
                if index < len(segment_paths) - 1:
                    append_silence(output, int(target_rate * 0.55))


def mux_narration(video_path: Path, narration_path: Path) -> None:
    """将旁白封装到 MP4 中；音轨不足时静音补齐至视频结束。"""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    temporary_output = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}-temp.mp4")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(narration_path),
            "-filter:a",
            "apad",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(temporary_output),
        ],
        check=True,
    )
    temporary_output.replace(OUTPUT_PATH)


def build_video() -> None:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"未找到中文字体：{FONT_PATH}")

    slides = [
        (title_slide(), 4.0),
        (prepare_slide(), 6.0),
        (analysis_slide(), 8.0),
        (review_slide(), 7.0),
        (mail_slide(), 8.0),
        (naming_slide(), 7.0),
        (finish_slide(), 7.0),
        (closing_slide(), 4.0),
    ]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(SILENT_OUTPUT_PATH),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise RuntimeError("无法初始化 MP4 视频编码器。")
    try:
        for slide, seconds in slides:
            for frame in frames_for_slide(slide, seconds):
                writer.write(frame)
    finally:
        writer.release()
    narration_path = ROOT / "docs" / "发票管理系统操作教学视频-v1.0.7-旁白.wav"
    build_narration_track(narration_path)
    mux_narration(SILENT_OUTPUT_PATH, narration_path)
    narration_path.unlink(missing_ok=True)
    SILENT_OUTPUT_PATH.unlink(missing_ok=True)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    build_video()
