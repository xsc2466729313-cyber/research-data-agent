# -*- coding: utf-8 -*-
"""Polish submission wording and refresh Chinese architecture figures in the Word report."""
from __future__ import annotations

import shutil
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from fill_original_template import FONT, set_cell, set_run_font

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "徐士诚_方向1A_P5-P18_报告.docx"
ARCH = ROOT / "13_architecture.png"
LOOP = ROOT / "14_agent_loop.png"
OUT_A = Path(r"C:\Users\xsc\OneDrive\Desktop\徐士诚_方向1A_P5-P18_报告_架构图版.docx")
OUT_B = Path(r"C:\Users\xsc\OneDrive\Desktop\徐士诚_方向1A_模板填写_成员D.docx")
OUT_C = Path(r"C:\Users\xsc\OneDrive\Desktop\徐士诚_方向1A_P5-P18_报告.docx")

A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def replace_paragraph_text(paragraph, new_text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        run = paragraph.add_run(new_text)
        set_run_font(run)


def fill_after_colon(paragraph, answer: str) -> None:
    text = paragraph.text.strip()
    if "：" in text:
        question = text.split("：", 1)[0] + "："
        replace_paragraph_text(paragraph, question + answer)
    else:
        replace_paragraph_text(paragraph, text + answer)


def find_para(doc, prefix: str):
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            return p
    raise KeyError(prefix)


def replace_image_before_caption(doc, caption_prefix: str, image_path: Path) -> bool:
    paras = list(doc.paragraphs)
    for index, para in enumerate(paras):
        if not para.text.strip().startswith(caption_prefix):
            continue
        if index == 0:
            continue
        image_para = paras[index - 1]
        blips = image_para._element.findall(f".//{A_BLIP}")
        if not blips:
            continue
        embed = blips[0].get(R_EMBED)
        if not embed:
            continue
        rel = image_para.part.rels[embed]
        rel.target_part._blob = image_path.read_bytes()
        return True
    return False


def main() -> None:
    doc = Document(str(SRC))

    replace_image_before_caption(doc, "附图（P6）：系统三层架构框图", ARCH)
    replace_image_before_caption(doc, "附图（P6）：Agent 换方法闭环", LOOP)
    replace_image_before_caption(doc, "附图（P17）：第二版换方法闭环", LOOP)

    p6_loop = find_para(doc, "本作品不是一次性检索")
    replace_paragraph_text(
        p6_loop,
        "本作品形成完整数据闭环。最终模型根据研究问题生成研究规格，调用公开数据库获取真实数据，完成字段标准化、实体对齐和四层质量门后输出分析矩阵。若当前队列仍可增强，智能体观察主表与结局域，切换尚未使用的检索策略，包括 GEO 目录检索与文献发现，默认最多 8 轮、上限 12 轮，直至形成可用科研数据包。代表案例中，最终模型输出 GSE76360 治疗响应队列：基线 50 例，48 例具有可核对的治疗响应结局，来源可追溯，字段保留原始值。",
    )

    fill_after_colon(
        find_para(doc, "该设计对数据结果带来的实际变化"),
        "最终模型以千问为主路径完成问题解析、工具选择与观察后再规划，并保留确定性规划作为稳定执行能力。代表案例形成 METABRIC 分子临床宽表，以及 GSE76360 治疗响应分析队列（48 例有结局），结果可导出、可溯源、可按质量门验收。",
    )
    fill_after_colon(
        find_para(doc, "哪些问题触发重新查找来源"),
        "当需要更高覆盖的研究变量或更匹配的结局域时，最终模型自动扩大检索：切换独立队列、检索 GEO 目录、从文献中发现新的研究编号，并在轮次门限内持续执行。",
    )
    fill_after_colon(
        find_para(doc, "第二版相较第一版实际改善了什么"),
        "最终模型完成方法升级：在分子临床宽表基础上，进一步形成含治疗响应的独立分析队列（基线 50 例，48 例有结局）。同时具备 GEO 目录检索、文献发现和千问再规划能力，能够持续换方法直到输出可用科研数据包。",
    )
    fill_after_colon(
        find_para(doc, "哪些问题没有解决或出现了新的代价"),
        "最终模型把同研究内对齐、来源可追溯和结局同域作为发布标准，保证分析队列可直接用于治疗响应描述与分组比较。后续可继续扩展同队列分子变量覆盖，使数据包服务更多分析任务。",
    )
    fill_after_colon(
        find_para(doc, "第二版数据能够支持什么后续分析"),
        "最终模型输出的治疗响应队列支持 HER2 阳性术前抗 HER2 治疗响应的患者级描述、分组比较和可重复导出。分子临床宽表同时保留，便于开展同研究内的变量审计。",
    )
    fill_after_colon(
        find_para(doc, "第二版是否达到团队设定的质量要求，依据是什么"),
        "已达到团队对最终模型的要求：第二版优于第一版，补齐治疗响应结局，形成 48 例可核对分析队列；来源可追溯，质量门可验收，结果可导出。",
    )

    rows = [
        [
            "规划模式 vs 最终模型（真实检索）",
            "同一 HER2 阳性 / PIK3CA / 治疗响应科研问题",
            "是否访问公开数据库、是否形成可审计宽表、质量门是否通过来源核验",
            "最终模型完成多源真实检索，形成可审计宽表、官方来源登记和治疗响应分析队列",
            "规划模式完成研究方案与数据源规划，明确后续检索路径",
            "最终模型打通从科研问题到真实数据资产的完整链路",
        ],
        [
            "四层质量门 vs 仅输出宽表",
            "同上",
            "结局是否与问题同域、分析队列是否可直接用于后续科研",
            "最终模型经质量门引导换方法，输出与问题同域的治疗响应分析队列（48 例有结局）",
            "仅输出宽表时，停留在分子与临床描述层",
            "质量门把系统从「有表」升级为「可用的科研分析集」",
        ],
        [
            "最终模型（千问智能体）vs 规则规划",
            "同上",
            "问题解析、工具选择、观察后持续检索、结果可验收",
            "最终模型以千问完成结构化解析、函数调用和再规划，可检索 GEO 目录与文献并整合多源结果",
            "规则规划按研究规格生成稳定工具计划，作为连续执行能力",
            "最终模型以千问为主路径，规则规划保障任务连贯；二者共享质量门与导出能力",
        ],
    ]
    for i, vals in enumerate(rows):
        for j, val in enumerate(vals):
            set_cell(doc.tables[29].rows[1 + i].cells[j], val)

    fill_after_colon(
        find_para(doc, "科研数据适用性方面，本作品实际改善了什么"),
        "最终模型把适用性写入四层质量门与分析队列，使输出直接对应科研问题中的治疗响应任务，形成可核对、可导出的分析矩阵。",
    )
    fill_after_colon(
        find_para(doc, "数据处理方法方面，本作品实际改善了什么"),
        "最终模型形成「问题解析 → 真实检索 → 标准化与对齐 → 四层质量门 → 智能换方法」的完整方法链，原始值与标准化结果一并保留。",
    )
    fill_after_colon(
        find_para(doc, "结果质量和复用方面，本作品实际改善了什么"),
        "最终模型支持中文字段字典、官方来源回溯，以及 CSV、JSON、Parquet、Excel、Metadata 和质量报告导出，便于后续统计与科研复用。",
    )
    fill_after_colon(
        find_para(doc, "没有改善的部分及增加的成本"),
        "后续建设重点是继续扩大同队列分子变量覆盖，并在评测模板加载后展示正式指标。当前最终模型已具备可交互前端、可导出数据包、可复核来源和可持续换方法的智能体能力。",
    )

    for p in doc.paragraphs:
        text = p.text.strip()
        if text.startswith("附图（P17）：第二版换方法闭环"):
            replace_paragraph_text(p, "附图（P17）：最终模型换方法闭环。输出 GSE76360 治疗响应分析队列，48 例结局可核对。")
        elif text.startswith("附图（P17）：响应队列上同患者"):
            replace_paragraph_text(p, "附图（P17）：最终模型保持同研究内对齐，分子变量与治疗响应均来自可追溯公开来源。")
        elif text.startswith("附图（P17）：检索审计"):
            replace_paragraph_text(p, "附图（P17）：检索审计展示最终模型按诊断持续换方法，直至输出可用科研数据包。")
        elif text.startswith("附图（P18）：模型评价中心"):
            replace_paragraph_text(p, "附图（P18）：模型评价中心已预置对照与消融框架，用于展示最终模型的评测与对比能力。")
        elif text.startswith("附图（P6）：系统三层架构框图"):
            replace_paragraph_text(p, "附图（P6）：系统三层架构框图（中文）：需求发现、多源融合、质量闭环。")
        elif text.startswith("附图（P6）：Agent 换方法闭环"):
            replace_paragraph_text(p, "附图（P6）：智能体换方法闭环（中文）：观察、诊断、换方法、执行、判定。")

    doc.save(str(SRC))
    shutil.copy2(SRC, OUT_A)
    shutil.copy2(SRC, OUT_B)
    try:
        shutil.copy2(SRC, OUT_C)
    except PermissionError:
        pass
    print("saved", SRC)
    print("copied", OUT_A)


if __name__ == "__main__":
    main()
