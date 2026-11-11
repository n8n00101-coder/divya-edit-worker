"""
motion_graphics.py — Divya motion-graphics template catalogue (v32).

MG is the dict Divya's codegen lists when it chooses a motion-graphics
template for a scene: template name -> one-line description.

Every entry maps to something the renderer can ACTUALLY draw — the
parenthesised source is where the drawing lives:
  * create.py  — draw_visual() kinds (counter, bar, donut, versus,
                 checklist, quote_card, document, bar_compare) and the
                 long-form lower_third
  * doc.py     — doc.label() for the big headline
  * effects.py — FX count_up / ring_fill / bar_grow helpers
  * visuals_lib (hark-kit/video_visuals_example.py) — timeline_cards,
                 balance_scale, document, india_map, photo_frame,
                 speech_bubble

Do not add a template here unless the renderer can draw it.
"""

MG = {
    "headline_pop": "big label pops word by word (doc.label)",
    "counter": "number counts up (create counter / FX count_up)",
    "bar_chart": "bars grow to values (create bar / bar_compare)",
    "donut": "ring fills to N percent (create donut)",
    "timeline": "events on a vertical line (visuals_lib timeline_cards)",
    "comparison": "two sides weighed (create versus / visuals_lib balance_scale)",
    "checklist": "boxes tick one by one (create checklist)",
    "quote_card": "big quote in a card (create quote_card)",
    "document": "official paper with real text (visuals_lib document)",
    "map_pin": "map outline with a pin (visuals_lib india_map)",
    "photo_frame": "real photo with slow Ken Burns zoom (visuals_lib photo_frame)",
    "lower_third": "name + title bar, bottom-left (create lower_third, long-form)",
    "callout": "speech bubble annotation (visuals_lib speech_bubble)",
}

__all__ = ["MG"]

if __name__ == "__main__":
    assert len(MG) == 13, f"MG must have 13 templates, got {len(MG)}"
    print(f"{len(MG)} templates")
    for name in MG:
        print(f"  - {name}")
