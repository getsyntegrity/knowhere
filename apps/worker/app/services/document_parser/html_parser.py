"""
HTML rendering utilities for DataFrame to HTML conversion.

This module provides functions for converting pandas DataFrames to HTML tables
with support for:
- MultiIndex columns with colspan/rowspan merging
- Row headers (semantic <th scope="row"> elements)
- Proper HTML escaping and formatting
- DOCX table to HTML conversion
- HTML to DataFrame/Markdown conversion
"""

import pandas as pd
from typing import Union, List
from bs4 import BeautifulSoup
from docx.table import Table as DocxTable
from shared.utils.text_utils import remove_duplicates_orderkept
from shared.core.exceptions.domain_exceptions import TableParsingException


def parse_nested_htmltb(table):
    """Parse nested HTML table into a list of rows.
    
    Handles nested tables recursively.
    
    Args:
        table: BeautifulSoup table element
        
    Returns:
        List of rows, where each row is a list of cell values or nested tables
    """
    rows = []
    for tr in table.find_all("tr", recursive=False):
        row = []
        for td in tr.find_all(["td", "th"], recursive=False):
            inner_table = td.find("table")
            if inner_table:
                row.append(parse_nested_htmltb(inner_table))
            else:
                row.append(td.get_text(strip=True))
        if row:
            rows.append(row)
    return rows


def html_to_md_lines(html: str):
    """Convert HTML table to list of markdown-like lines.
    
    Args:
        html: HTML string containing a table
        
    Returns:
        List of strings, each representing a row with cells separated by ' | '
    """
    soup = BeautifulSoup(html, 'html.parser')
    lines = []
    for row in soup.find_all("tr"):
        row_text = []
        for cell in row.find_all("td", recursive=False):
            text = cell.get_text(separator=' ', strip=True)
            if text:
                row_text.append(text)
        if row_text:
            lines.append(" | ".join(row_text))
    lines = remove_duplicates_orderkept(lines)
    return lines


def tb_htmlstr_to_df(html_str):
    """Convert first table in HTML string to DataFrame"""
    soup = BeautifulSoup(html_str, "html.parser")
    table = soup.find("table")
    if not table:
        raise TableParsingException(
            user_message="No table structure found in the document",
            reason="INVALID_FORMAT",
            internal_message="No <table> found in the HTML string"
        )
    nested_list = parse_nested_htmltb(table)
    try:
        df = pd.DataFrame(nested_list[1:], columns=nested_list[0])
    except Exception:
        df = pd.DataFrame(nested_list)
    return df

    
def table2html(table: DocxTable) -> str:
    """Convert a DOCX table to HTML string.
    
    Handles nested tables recursively.
    
    Args:
        table: python-docx Table object
        
    Returns:
        HTML string representation of the table
    """
    html = "<table border='1'>"
    for row in table.rows:
        html += "<tr>"
        for cell in row.cells:
            html += "<td>"
            if cell.tables:
                for nested_table in cell.tables:
                    html += table2html(nested_table)
            else:
                html += cell.text.strip().replace('\n', '<br>')
            html += "</td>"
        html += "</tr>"
    html += "</table>"
    return html


def render_multiindex_thead(columns: pd.MultiIndex, escape: bool = False) -> str:
    """
    Convert MultiIndex columns to HTML thead with colspan/rowspan.
    
    This function generates a proper multi-row <thead> structure where:
    - Horizontally adjacent identical values are merged with colspan
    - Vertically repeated values are merged with rowspan
    
    Args:
        columns: pandas MultiIndex representing the column headers
        escape: Whether to HTML-escape the cell values
        
    Returns:
        HTML string for the <thead> element
    """
    import html as html_lib
    
    n_levels = columns.nlevels
    n_cols = len(columns)
    
    # Build a 2D grid of values [level][col]
    grid = []
    for level in range(n_levels):
        row = [columns.get_level_values(level)[col] for col in range(n_cols)]
        grid.append(row)
    
    # Calculate colspan for each cell (horizontal merging)
    # colspan[level][col] = number of columns this cell spans
    colspan = [[1] * n_cols for _ in range(n_levels)]
    
    for level in range(n_levels):
        col = 0
        while col < n_cols:
            span = 1
            while col + span < n_cols and grid[level][col] == grid[level][col + span]:
                # Check if the parent cells also match (for correct hierarchical merging)
                parent_match = True
                for parent_level in range(level):
                    if grid[parent_level][col] != grid[parent_level][col + span]:
                        parent_match = False
                        break
                if parent_match:
                    span += 1
                else:
                    break
            colspan[level][col] = span
            col += span
    
    # Calculate rowspan for each cell (vertical merging)
    # A cell has rowspan > 1 if all cells in the same column below have the same value
    # AND if they would have the same colspan
    rowspan = [[1] * n_cols for _ in range(n_levels)]
    
    for col in range(n_cols):
        level = 0
        while level < n_levels:
            span = 1
            # Check if cells below have the same value AND same colspan
            while level + span < n_levels:
                if (grid[level][col] == grid[level + span][col] and 
                    colspan[level][col] == colspan[level + span][col]):
                    span += 1
                else:
                    break
            rowspan[level][col] = span
            level += span
    
    # Build HTML rows
    # Track which cells are "covered" by rowspan from above
    covered = [[False] * n_cols for _ in range(n_levels)]
    
    html_parts = ['<thead>']
    
    for level in range(n_levels):
        html_parts.append('<tr style="text-align: center;">')
        col = 0
        while col < n_cols:
            if covered[level][col]:
                # This cell is covered by a rowspan from above, skip it
                col += 1
                continue
            
            # Get cell value
            val = grid[level][col]
            val_str = str(val) if val is not None else ''
            if escape:
                val_str = html_lib.escape(val_str)
            
            # Get spans
            cs = colspan[level][col]
            rs = rowspan[level][col]
            
            # Mark covered cells
            for r_offset in range(rs):
                for c_offset in range(cs):
                    if r_offset > 0 or c_offset > 0:
                        if level + r_offset < n_levels and col + c_offset < n_cols:
                            covered[level + r_offset][col + c_offset] = True
            
            # Build th element with attributes
            attrs = []
            if cs > 1:
                attrs.append(f'colspan="{cs}"')
            if rs > 1:
                attrs.append(f'rowspan="{rs}"')
            
            attr_str = ' ' + ' '.join(attrs) if attrs else ''
            html_parts.append(f'<th{attr_str}>{val_str}</th>')
            
            col += cs
        
        html_parts.append('</tr>')
    
    html_parts.append('</thead>')
    return ''.join(html_parts)


def render_tbody_with_row_headers(tb_df: pd.DataFrame, row_header_cols: int = 0, 
                                   na_rep: str = "—", escape: bool = False) -> str:
    """
    Render DataFrame body with support for row headers and cell merging.
    
    This function generates a proper <tbody> structure where:
    - Row header columns use <th scope="row"> instead of <td>
    - Horizontally adjacent identical values in row headers are merged with colspan
    - Vertically adjacent identical values in row headers are merged with rowspan
    - Merging respects hierarchical structure
    
    Args:
        tb_df: DataFrame to render
        row_header_cols: Number of leftmost columns to render as <th scope="row">
        na_rep: String representation for NaN values
        escape: Whether to HTML-escape values
        
    Returns:
        HTML string for the <tbody> element
    """
    import html as html_lib
    
    if row_header_cols <= 0:
        # No row headers - simple rendering without merging
        html_parts = ['<tbody>']
        for _, row in tb_df.iterrows():
            html_parts.append('<tr>')
            for val in row:
                if pd.isna(val):
                    val_str = na_rep
                else:
                    val_str = str(val)
                if escape:
                    val_str = html_lib.escape(val_str)
                html_parts.append(f'<td>{val_str}</td>')
            html_parts.append('</tr>')
        html_parts.append('</tbody>')
        return ''.join(html_parts)
    
    n_rows = len(tb_df)
    n_cols = len(tb_df.columns)
    
    if n_rows == 0:
        return '<tbody></tbody>'
    
    # Build 2D grid of values for row header columns
    # grid[row_idx][col_idx] = value
    grid = []
    for row_idx in range(n_rows):
        row_values = []
        for col_idx in range(row_header_cols):
            val = tb_df.iloc[row_idx, col_idx]
            if pd.isna(val):
                val = na_rep
            else:
                val = str(val)
            row_values.append(val)
        grid.append(row_values)
    
    # Calculate colspan for each cell (horizontal merging within same row)
    # colspan[row_idx][col_idx] = number of columns this cell spans
    colspan = [[1] * row_header_cols for _ in range(n_rows)]
    
    for row_idx in range(n_rows):
        col_idx = 0
        while col_idx < row_header_cols:
            span = 1
            while col_idx + span < row_header_cols and grid[row_idx][col_idx] == grid[row_idx][col_idx + span]:
                span += 1
            colspan[row_idx][col_idx] = span
            col_idx += span
    
    # Calculate rowspan for each cell (vertical merging)
    # Only calculate rowspan for cells that start a colspan group
    # rowspan[row_idx][col_idx] = number of rows this cell spans
    rowspan = [[1] * row_header_cols for _ in range(n_rows)]
    
    col_idx = 0
    while col_idx < row_header_cols:
        row_idx = 0
        while row_idx < n_rows:
            # Only process cells that start a colspan group (not covered by colspan from left)
            if col_idx > 0 and grid[row_idx][col_idx] == grid[row_idx][col_idx - 1]:
                row_idx += 1
                continue
            
            current_colspan = colspan[row_idx][col_idx]
            span = 1
            
            while row_idx + span < n_rows:
                # Check if the value matches
                if grid[row_idx][col_idx] != grid[row_idx + span][col_idx]:
                    break
                # Check if colspan in the next row also matches
                if colspan[row_idx + span][col_idx] != current_colspan:
                    break
                # Check if all parent columns (to the left) also have same rowspan behavior
                parent_match = True
                for parent_col in range(col_idx):
                    if grid[row_idx][parent_col] != grid[row_idx + span][parent_col]:
                        parent_match = False
                        break
                if parent_match:
                    span += 1
                else:
                    break
            
            rowspan[row_idx][col_idx] = span
            row_idx += span
        col_idx += 1
    
    # Track which cells are covered by rowspan from above or colspan from left
    covered = [[False] * row_header_cols for _ in range(n_rows)]
    
    # Mark cells covered by colspan (horizontal)
    for row_idx in range(n_rows):
        col_idx = 0
        while col_idx < row_header_cols:
            cs = colspan[row_idx][col_idx]
            for offset in range(1, cs):
                if col_idx + offset < row_header_cols:
                    covered[row_idx][col_idx + offset] = True
            col_idx += cs
    
    # Mark cells covered by rowspan (vertical)
    for row_idx in range(n_rows):
        for col_idx in range(row_header_cols):
            if covered[row_idx][col_idx]:
                continue  # Skip cells already covered by colspan
            rs = rowspan[row_idx][col_idx]
            for offset in range(1, rs):
                if row_idx + offset < n_rows:
                    # Mark all cells in the rowspan as covered
                    cs = colspan[row_idx][col_idx]
                    for c_offset in range(cs):
                        if col_idx + c_offset < row_header_cols:
                            covered[row_idx + offset][col_idx + c_offset] = True
    
    # Build HTML
    html_parts = ['<tbody>']
    
    for row_idx in range(n_rows):
        html_parts.append('<tr>')
        
        # Render row header columns with rowspan/colspan
        for col_idx in range(row_header_cols):
            if covered[row_idx][col_idx]:
                # This cell is covered by a rowspan/colspan, skip it
                continue
            
            val_str = grid[row_idx][col_idx]
            if escape:
                val_str = html_lib.escape(val_str)
            
            rs = rowspan[row_idx][col_idx]
            cs = colspan[row_idx][col_idx]
            
            attrs = []
            if rs > 1:
                attrs.append(f'rowspan="{rs}"')
            if cs > 1:
                attrs.append(f'colspan="{cs}"')
            
            attr_str = ' ' + ' '.join(attrs) if attrs else ''
            html_parts.append(f'<th scope="row"{attr_str}>{val_str}</th>')
        
        # Render data columns
        for col_idx in range(row_header_cols, n_cols):
            val = tb_df.iloc[row_idx, col_idx]
            if pd.isna(val):
                val_str = na_rep
            else:
                val_str = str(val)
            if escape:
                val_str = html_lib.escape(val_str)
            html_parts.append(f'<td>{val_str}</td>')
        
        html_parts.append('</tr>')
    
    html_parts.append('</tbody>')
    return ''.join(html_parts)





def df2html(tb_df: pd.DataFrame,
    *,
    index: bool = False,
    classes: Union[str, List[str], None] = "table table-striped",
    na_rep: str = "—",
    escape: bool = False,
    row_header_cols: int = 0
    ) -> str:
    """Convert DataFrame to HTML table.
    
    Supports:
    - MultiIndex columns with proper colspan/rowspan merging
    - Row headers (leftmost columns rendered as <th scope="row">)
    - Custom CSS classes and NA representation
    
    Args:
        tb_df: DataFrame to convert
        index: Whether to include the DataFrame index (not commonly used)
        classes: CSS classes to add to the table
        na_rep: String representation for NaN values
        escape: Whether to HTML-escape values
        row_header_cols: Number of leftmost columns to render as row headers (<th>).
                        These columns will use <th scope="row"> instead of <td>.
                        
    Returns:
        HTML table string
    """
    class_str = classes if isinstance(classes, str) else ' '.join(classes) if classes else ''
    
    # Check if columns are MultiIndex - use advanced rendering
    if isinstance(tb_df.columns, pd.MultiIndex):
        # Use specialized rendering for MultiIndex columns
        thead_html = render_multiindex_thead(tb_df.columns, escape=escape)
        tbody_html = render_tbody_with_row_headers(tb_df, row_header_cols, na_rep, escape)
        return f'<table class="dataframe {class_str}">{thead_html}{tbody_html}</table>'
    
    # Simple columns case
    if row_header_cols <= 0:
        # Use default pandas to_html for simple case without row headers
        table_html = tb_df.to_html(
            index=index,
            na_rep=na_rep,
            classes=classes,
            escape=escape,
            border=0,
            justify="center",
        )
        return table_html.replace('\n', '')
    
    # Simple columns with row headers - custom rendering
    import html as html_lib
    
    html_parts = [f'<table class="dataframe {class_str}">']
    
    # Build thead
    html_parts.append('<thead>')
    html_parts.append('<tr style="text-align: center;">')
    for col in tb_df.columns:
        col_str = str(col) if col is not None else ''
        if escape:
            col_str = html_lib.escape(col_str)
        html_parts.append(f'<th>{col_str}</th>')
    html_parts.append('</tr>')
    html_parts.append('</thead>')
    
    # Build tbody with row headers
    tbody_html = render_tbody_with_row_headers(tb_df, row_header_cols, na_rep, escape)
    html_parts.append(tbody_html)
    
    html_parts.append('</table>')
    
    return ''.join(html_parts)
