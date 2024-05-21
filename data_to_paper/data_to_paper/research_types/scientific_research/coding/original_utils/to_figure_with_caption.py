def to_latex_figure_with_caption(figure, filename: str, caption: str, label: str, comment: str = None):
    """
    Save a figure with a caption and label.
    """
    figure.savefig(filename)
    latex = f"""
        \\begin{{figure}}[htbp]
        \\centering
        \\includegraphics[width=0.8\\textwidth]{{{filename.replace(".png", "")}}}
        \\caption{{{caption}}}
        \\label{{{label}}}
        \\end{{figure}}
    """
    if comment:
        latex = comment + latex
    with open(filename.replace('.png', '.tex'), 'w') as f:
        f.write(latex)
    return latex


def get_figure_and_caption_as_html(figure, filename: str, caption: str, comment: str = None):
    """
    Save a figure with a caption and label.
    """
    figure.savefig(filename)
    html = f"""
        <div>
        <img src="{filename}" alt="{caption}" />
        <p>{caption}</p>
        </div>
    """
    if comment:
        html = comment + html
    with open(filename.replace('.png', '.html'), 'w') as f:
        f.write(html)
    return html
