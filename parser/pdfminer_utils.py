"""PDF layout helpers for HSBC HK eStatement parsing (Python 3 port)."""

from __future__ import annotations

import math
import re
from io import BytesIO
from warnings import warn

import pandas as pd
from pdfminer.converter import PDFPageAggregator, TextConverter
from pdfminer.layout import LAParams, LTLine, LTTextBoxHorizontal, LTTextLineHorizontal
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser


def get_layouts(fname: str) -> list:
    with open(fname, "rb") as fp:
        data = fp.read()

    cstr = BytesIO(data)
    doc = PDFDocument(PDFParser(cstr))
    rsrcmgr = PDFResourceManager()
    laparams = LAParams(line_margin=0.000001, char_margin=1)
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)

    layouts = []
    for page in PDFPage.create_pages(doc):
        interpreter.process_page(page)
        layouts.append(device.get_result())
    return layouts


def get_pages_content(layouts, header_re, footer_re, v_margin=1):
    pages = []
    for layout in layouts:
        objs = layout._objs
        footer_matches = find_text(objs, footer_re)
        footer_obj = get_bottom_most(footer_matches)

        header_matches = find_text(objs, header_re)
        header_obj = get_top_most(header_matches)

        x0 = min(obj.bbox[0] for obj in objs)
        x1 = max(obj.bbox[2] for obj in objs)
        y0 = footer_obj.bbox[3]
        y1 = header_obj.bbox[1]

        bbox = (x0, y0 + v_margin, x1, y1 - v_margin)
        pages.append(get_objs_in_bound(objs, bbox))
    return pages


def find_text(objs, regexp):
    pattern = re.compile(regexp)
    objs_fnd = []
    for obj in objs:
        try:
            if pattern.search(obj.get_text()):
                objs_fnd.append(obj)
        except (AttributeError, TypeError):
            pass
    return objs_fnd


def pt_in_bbox(pt, bbox):
    return bbox[0] <= pt[0] <= bbox[2] and bbox[1] <= pt[1] <= bbox[3]


def get_objs_in_bound(objs, bbox, types=None, partial=True):
    ans = []
    for obj in objs:
        if types is not None and type(obj) not in types:
            continue
        pts = [(obj.x0, obj.y0), (obj.x0, obj.y1), (obj.x1, obj.y0), (obj.x1, obj.y1)]
        pts_in = [pt_in_bbox(pt, bbox) for pt in pts]
        is_in = any(pts_in) if partial else all(pts_in)
        if is_in:
            ans.append(obj)
    return ans


def union_bbox(bbox1, bbox2):
    return (
        min(bbox1[0], bbox2[0]),
        min(bbox1[1], bbox2[1]),
        max(bbox1[2], bbox2[2]),
        max(bbox1[3], bbox2[3]),
    )


def get_top_most(objs):
    top_obj = objs[0]
    for obj in objs:
        if obj.y1 > top_obj.y1:
            top_obj = obj
        elif obj.y1 == top_obj.y1 and obj.x0 < top_obj.x0:
            top_obj = obj
    return top_obj


def get_bottom_most(objs):
    bottom_obj = objs[0]
    for obj in objs:
        if obj.y0 < bottom_obj.y0:
            bottom_obj = obj
        elif obj.y0 == bottom_obj.y0 and obj.x1 > bottom_obj.x1:
            bottom_obj = obj
    return bottom_obj


def get_text_lines(objs):
    lines = []
    for obj in objs:
        if isinstance(obj, LTTextLineHorizontal):
            lines.append(obj)
        elif isinstance(obj, LTTextBoxHorizontal):
            lines.extend(get_text_lines(obj._objs))
    return lines


def get_table(objs, v_margin=5.0):
    objs = get_text_lines(objs)
    if not objs:
        return None

    objs = sorted(objs, key=lambda a: a.x0)
    col_num = 0
    cols = {}
    bound = [objs[0].x0, objs[0].x1]
    for obj in objs:
        if obj.x0 <= bound[1]:
            bound[1] = max(bound[1], obj.x1)
        else:
            col_num += 1
            bound = [obj.x0, obj.x1]
        cols[obj] = col_num

    objs = sorted(objs, key=lambda a: a.y0)
    row_num = 0
    rows = {}
    bound = [objs[0].y0, objs[0].y1 - v_margin]
    for obj in objs:
        if obj.y0 <= bound[1]:
            bound[1] = max(bound[1], obj.y1 - v_margin)
        else:
            row_num += 1
            bound = [obj.y0, obj.y1 - v_margin]
        rows[obj] = row_num

    max_row = max(rows[obj] for obj in rows)
    max_col = max(cols[obj] for obj in cols)
    for obj in rows:
        rows[obj] = (rows[obj] - max_row) * -1

    table = [[None] * (max_col + 1) for _ in range(max_row + 1)]
    for obj in objs:
        r, c = rows[obj], cols[obj]
        table[r][c] = obj.get_text().replace("\n", " ").strip()

    return pd.DataFrame(table[1 : len(table)], columns=table[0])


def get_connected_lines(objs, epsilon=0.0):
    line_objs = [obj for obj in objs if isinstance(obj, LTLine)]
    vertices = []
    for obj in line_objs:
        vertices.append((obj.x0, obj.y0, obj))
        vertices.append((obj.x1, obj.y1, obj))

    dists = []
    for i in range(len(vertices)):
        for j in range(i + 1, len(vertices)):
            a = vertices[i]
            b = vertices[j]
            dist = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
            dists.append((dist, a[2], b[2]))

    dists = [item for item in dists if item[0] <= epsilon]
    chains = {}
    for dist, a, b in dists:
        if a not in chains and b not in chains:
            chain = [a, b]
            chains[a] = chain
            chains[b] = chain
        elif a in chains and b not in chains:
            chains[a].append(b)
            chains[b] = chains[a]
        elif a not in chains and b in chains:
            chains[b].append(a)
            chains[a] = chains[b]
        elif chains[a] != chains[b]:
            chain = chains[a]
            for obj in chains[b]:
                chain.append(obj)
                chains[obj] = chain

    polygons = chains.values()
    return list({id(x): x for x in polygons}.values())


def get_bbox(objs):
    bbox = objs[0].bbox
    for obj in objs:
        bbox = (
            min(obj.bbox[0], bbox[0]),
            min(obj.bbox[1], bbox[1]),
            max(obj.bbox[2], bbox[2]),
            max(obj.bbox[3], bbox[3]),
        )
    return bbox


def get_underlined_text(pages, v_margin=2, h_margin=5, line_width_max=1):
    ans = []
    for i, page in enumerate(pages):
        text_objs = [obj for obj in page if isinstance(obj, LTTextBoxHorizontal)]
        line_objs = [obj for obj in page if isinstance(obj, LTLine)]

        for text in text_objs:
            underlined = False
            for line in line_objs:
                x_matched = text.bbox[0] >= (line.bbox[0] - h_margin) and text.bbox[2] <= (
                    line.bbox[2] + h_margin
                )
                y_matched = abs(text.bbox[1] - line.bbox[3]) <= v_margin
                width_match = line.linewidth <= line_width_max
                underlined |= x_matched and y_matched and width_match

            if underlined:
                ans.append({"Page": i, "Text": text.get_text().rstrip(), "BBox": text.bbox})
    return ans


def get_text_in_boxes(pages, epsilon=1.1):
    headers = []
    for i, page in enumerate(pages):
        page_headers = []
        polygons = get_connected_lines(page, epsilon=epsilon)
        bboxes = sorted((get_bbox(poly) for poly in polygons), key=lambda x: -x[1])

        for bbox in bboxes:
            objs = get_objs_in_bound(page, bbox, types={LTTextBoxHorizontal})
            objs = [obj for obj in objs if obj and len(obj.get_text().strip()) > 0]
            if len(objs) == 1:
                title = objs[0].get_text().rstrip()
                bbox = union_bbox(bbox, get_bbox(objs))
                page_headers.append({"Page": i, "Text": title, "BBox": bbox})
            elif len(objs) > 1:
                warn(f"Ignoring unexpected number of text objects in section header page {i}")

        page_headers = sorted(page_headers, key=lambda x: -x["BBox"][1])
        headers.extend(page_headers)
    return headers


def sectionize(pages, headers):
    epsilon = 1
    sections = []
    for i, header in enumerate(headers):
        page_start = header["Page"]
        y1_start = header["BBox"][1]

        if i == len(headers) - 1:
            page_end = len(pages) - 1
            y0_end = get_bbox(pages[page_end])[1]
        else:
            page_end = headers[i + 1]["Page"]
            y0_end = headers[i + 1]["BBox"][3]

        page_objs = []
        for j in range(page_start, page_end + 1):
            bbox = get_bbox(pages[j])
            x0, x1 = bbox[0], bbox[2]
            y1 = y1_start if j == page_start else bbox[3]
            y0 = y0_end if j == page_end else bbox[1]
            inner_bbox = (x0, y0 + epsilon, x1, y1 - epsilon)
            page_objs.append(get_objs_in_bound(pages[j], inner_bbox))

        sections.append({"Text": header["Text"], "Pages": page_objs})
    return sections


def single_val(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 0:
        return None
    raise ValueError("More than 1 unique value passed to single_val")
