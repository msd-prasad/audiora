from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


OUTPUT = Path("output/pdf/audiora-raw-story-test.pdf")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=0.8 * inch,
        leftMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="The Lighthouse Signal",
        author="Audiora Sample Story",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StoryTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=29,
        textColor=HexColor("#1B3556"),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
        fontSize=10,
        leading=14,
        textColor=HexColor("#60738A"),
        spaceAfter=22,
    )
    body_style = ParagraphStyle(
        "StoryBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11.5,
        leading=17,
        textColor=HexColor("#1F2937"),
        spaceAfter=13,
    )

    paragraphs = [
        "On the first evening of the autumn storm, Nina Vale noticed that the old lighthouse on Gull Point was shining again. The tower had been closed for ten years, and everyone in the small coastal town knew its lamp no longer worked. From the window of her father’s repair shop, Nina saw one white flash, then two more, cutting across the rain. Her younger brother Leo wanted to run there at once. Nina made him put on his yellow raincoat first, then grabbed her own torch and the small radio their father used during power cuts.",
        "The path to the lighthouse was slippery and loud with waves. At the iron gate, they found Marisol Reed, the retired lighthouse keeper, trying to hold the gate shut against the wind. Marisol looked tired but calm. She told them that a fishing boat had lost its navigation system near the rocks. Its captain had sent a weak message over the radio, and the lighthouse lamp was the only signal that could guide the boat safely into the harbour. The backup generator had started, but the lamp’s turning wheel was stuck.",
        "Inside the tower, Nina smelled wet stone, old oil, and salt. Leo held the torch while Marisol climbed the narrow stairs. At the top, the great glass lamp was glowing, but it faced the same patch of black sea. Nina looked at the gears below it and remembered how her father cleaned the moving parts of old clocks. She found a length of fishing line tangled around one gear, wet and tight like a knot. While Marisol steadied the lamp, Nina carefully cut the line with the small tool from her key ring.",
        "The wheel moved with a low click. Light began to sweep across the water in a slow, bright circle. A few minutes later, the radio crackled with the captain’s voice: he could see the signal and was following it home. Nina, Leo, and Marisol stood together at the window until the boat’s warm lights appeared beyond the harbour wall. When the storm finally softened, Marisol placed the old lighthouse key in Nina’s hand. “A place like this needs someone who notices when it is needed,” she said. Nina looked at the tower, the sea, and her grinning brother, and knew she would come back tomorrow.",
    ]

    flowables = [
        Paragraph("The Lighthouse Signal", title_style),
        Paragraph("An original short story for Audiora raw-story PDF testing", subtitle_style),
        Spacer(1, 4),
        *[Paragraph(paragraph, body_style) for paragraph in paragraphs],
    ]
    document.build(flowables)


if __name__ == "__main__":
    main()
