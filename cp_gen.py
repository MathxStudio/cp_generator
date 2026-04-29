from __future__ import annotations

import json
from pathlib import Path
import math
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter import font as tkfont

import numpy as np

import box_head_sample
import cp
import fold_sim


DEFAULT_POINTS = 8
MODEL_SIDE = 500


class CPGeneratorApp:
    COLORS = {
        "shell": "#eef2f7",
        "panel": "#f7f9fc",
        "panel_alt": "#edf3fa",
        "card": "#ffffff",
        "ink": "#232629",
        "ink_soft": "#60656c",
        "border": "#d4dde7",
        "border_strong": "#bcc9d6",
        "accent": "#3daee9",
        "accent_hover": "#1d99f3",
        "accent_deep": "#147fc1",
        "accent_disabled": "#b9deef",
        "accent_text": "#ffffff",
        "secondary": "#f67400",
        "secondary_hover": "#df6a00",
        "secondary_deep": "#c55d00",
        "secondary_disabled": "#f0cfb3",
        "secondary_text": "#ffffff",
        "ink_button": "#31363b",
        "ink_button_hover": "#232629",
        "ink_button_disabled": "#a5b0ba",
        "neutral_button": "#e8edf4",
        "neutral_button_hover": "#dbe4ee",
        "neutral_button_disabled": "#f3f6fa",
        "neutral_button_text": "#31363b",
        "canvas_bg": "#f7fbff",
        "paper": "#ffffff",
        "square_outline": "#bcc8d4",
        "grid": "#e6edf5",
        "wash_one": "#eaf2fb",
        "wash_two": "#f6efe6",
        "pattern_line": "#d7e0ea",
        "shadow_1": "#dce4ed",
        "shadow_2": "#e8eef5",
        "status_bg": "#f3f7fb",
        "status_detail": "#6b7480",
        "vertex_fill": "#31363b",
        "vertex_edge": "#ffffff",
        "label_bg": "#f4f8fc",
        "label_outline": "#ccd7e2",
        "mountain": "#f67400",
        "valley": "#3daee9",
        "neutral_fold": "#7a7c7d",
        "preview_bg": "#f8fbff",
        "preview_glow": "#ffffff",
        "preview_wash": "#e5edf6",
        "preview_shadow": "#d7e2ee",
        "preview_shadow_deep": "#b8c7d6",
        "preview_surface": "#ffffff",
        "preview_back": "#e8eef5",
        "preview_wire": "#8a97a3",
        "preview_crease": "#b6c3cf",
    }
    EDGE_FAMILY_COLORS = (
        "#3daee9",
        "#f67400",
        "#6ea27b",
        "#7b8fb8",
        "#d18a6d",
        "#5f98a6",
    )

    BADGE_COLORS = {
        "neutral": ("#dfe8f2", "#31363b"),
        "working": ("#3daee9", "#ffffff"),
        "success": ("#1cdc9a", "#ffffff"),
        "warning": ("#fdbc4b", "#232629"),
        "danger": ("#ed1515", "#ffffff"),
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CP Generator")
        self.root.geometry("1460x900")
        self.root.minsize(1220, 780)
        self.root.configure(bg=self.COLORS["shell"])
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self.pattern = cp.CreasePattern()
        self.preview_model: fold_sim.FoldedFigureModel | None = None
        self.preview_reference_pattern: cp.CreasePattern | None = None
        self.sample_key: str | None = None
        self.fold_assignment_ready = False
        self._preview_job: str | None = None
        self._preview_direction = 1
        self._preview_orbit_yaw = 0.0
        self._preview_orbit_pitch = 0.0
        self._preview_orbit_roll = 0.0
        self._preview_zoom = 1.0
        self._preview_drag_last: tuple[int, int] | None = None
        self._busy = False

        self.point_count_var = tk.StringVar(value=str(DEFAULT_POINTS))
        self.show_labels_var = tk.BooleanVar(value=False)
        self.preview_loop_var = tk.BooleanVar(value=True)
        self.preview_edge_families_var = tk.BooleanVar(value=False)
        self.preview_progress_var = tk.DoubleVar(value=0.0)
        self.vertex_count_var = tk.StringVar(value="0")
        self.fold_count_var = tk.StringVar(value="0")
        self.interior_count_var = tk.StringVar(value="0")
        self.state_var = tk.StringVar(value="Fresh")
        self.status_var = tk.StringVar(value="Generate, optimize, and assign folds.")
        self.detail_var = tk.StringVar(
            value="The crease sheet and folded preview stay live as the geometry changes."
        )
        self.sheet_caption_var = tk.StringVar(
            value="Terracotta lines are mountains, blue lines are valleys, and graphite lines remain unassigned."
        )
        self.preview_caption_var = tk.StringVar(
            value="Assign mountain and valley folds to unlock the folded figure."
        )
        self.preview_detail_var = tk.StringVar(
            value="The preview uses the exact face solver when possible and a guarded mesh fallback when the sheet becomes numerically unstable."
        )
        self.preview_summary_var = tk.StringVar()
        self.preview_progress_text_var = tk.StringVar(value="Fold 0%")
        self.preview_button_var = tk.StringVar(value="Play Fold")
        self._interactive_widgets: list[ttk.Widget] = []
        self._preview_widgets: list[ttk.Widget] = []
        self._wrap_labels: list[tuple[tk.Widget, tk.Widget, int, int, int | None]] = []
        self._wrap_refresh_job: str | None = None
        self._closing = False

        self._build_fonts()
        self._configure_style()
        self._build_layout()
        self.preview_caption_var.trace_add("write", self._refresh_preview_summary)
        self.preview_detail_var.trace_add("write", self._refresh_preview_summary)
        self._refresh_preview_summary()
        self.root.bind("<Configure>", self._queue_wrap_refresh, add="+")
        self._refresh_wrap_lengths()
        self._set_status(
            "Fresh",
            "A new sheet is ready for exploration.",
            "Start with a point count on the left, then generate a new crease pattern.",
            tone="neutral",
        )
        self._sync_preview_controls()
        self.make_cp(initial=True)

    def _build_fonts(self) -> None:
        sans = self._pick_font_family(
            "Aptos",
            "Segoe UI",
            "SF Pro Display",
            "Helvetica Neue",
            "Noto Sans",
            "Liberation Sans",
            "DejaVu Sans",
        )
        mono = self._pick_font_family(
            "CaskaydiaCove Nerd Font Mono",
            "CaskaydiaCove NF",
            "CaskaydiaMono Nerd Font",
            "Cascadia Code",
            "JetBrainsMono Nerd Font",
            "DejaVu Sans Mono",
            "Consolas",
        )
        self.fonts = {
            "hero": tkfont.Font(family=sans, size=22, weight="bold"),
            "title": tkfont.Font(family=sans, size=15, weight="bold"),
            "section": tkfont.Font(family=sans, size=11, weight="bold"),
            "body": tkfont.Font(family=sans, size=10),
            "small": tkfont.Font(family=mono, size=9),
            "button": tkfont.Font(family=mono, size=10, weight="bold"),
            "stat_value": tkfont.Font(family=mono, size=15, weight="bold"),
            "badge": tkfont.Font(family=mono, size=10, weight="bold"),
            "stage_title": tkfont.Font(family=sans, size=18, weight="bold"),
            "stage_body": tkfont.Font(family=sans, size=11),
            "card_title": tkfont.Font(family=sans, size=13, weight="bold"),
            "preview_hero": tkfont.Font(family=sans, size=16, weight="bold"),
            "label": tkfont.Font(family=mono, size=9, weight="bold"),
        }

    def _pick_font_family(self, *choices: str) -> str:
        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            available = set()
        for choice in choices:
            if choice in available:
                return choice
        return "TkDefaultFont"

    def _configure_style(self) -> None:
        colors = self.COLORS
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=colors["shell"])
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure("Stage.TFrame", background=colors["panel_alt"])

        style.configure(
            "Hero.TLabel",
            background=colors["panel"],
            foreground=colors["ink"],
            font=self.fonts["hero"],
        )
        style.configure(
            "PanelTitle.TLabel",
            background=colors["panel"],
            foreground=colors["ink"],
            font=self.fonts["title"],
        )
        style.configure(
            "PanelBody.TLabel",
            background=colors["panel"],
            foreground=colors["ink"],
            font=self.fonts["body"],
        )
        style.configure(
            "PanelMuted.TLabel",
            background=colors["panel"],
            foreground=colors["ink_soft"],
            font=self.fonts["small"],
        )
        style.configure(
            "CardTitle.TLabel",
            background=colors["card"],
            foreground=colors["ink"],
            font=self.fonts["section"],
        )
        style.configure(
            "CardBody.TLabel",
            background=colors["card"],
            foreground=colors["ink"],
            font=self.fonts["body"],
        )
        style.configure(
            "CardMuted.TLabel",
            background=colors["card"],
            foreground=colors["ink_soft"],
            font=self.fonts["small"],
        )
        style.configure(
            "StageTitle.TLabel",
            background=colors["panel_alt"],
            foreground=colors["ink"],
            font=self.fonts["stage_title"],
        )
        style.configure(
            "StageBody.TLabel",
            background=colors["panel_alt"],
            foreground=colors["ink_soft"],
            font=self.fonts["stage_body"],
        )

        style.configure(
            "Modern.TEntry",
            padding=(12, 8),
            foreground=colors["ink"],
            fieldbackground=colors["card"],
            background=colors["card"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        style.map(
            "Modern.TEntry",
            bordercolor=[("focus", colors["accent"]), ("!focus", colors["border"])],
            lightcolor=[("focus", colors["accent"]), ("!focus", colors["border"])],
            darkcolor=[("focus", colors["accent"]), ("!focus", colors["border"])],
        )

        style.configure(
            "Modern.TCombobox",
            padding=(10, 7),
            foreground=colors["ink"],
            fieldbackground=colors["card"],
            background=colors["card"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            arrowsize=14,
        )
        style.map(
            "Modern.TCombobox",
            bordercolor=[("focus", colors["accent"]), ("!focus", colors["border"])],
            lightcolor=[("focus", colors["accent"]), ("!focus", colors["border"])],
            darkcolor=[("focus", colors["accent"]), ("!focus", colors["border"])],
            fieldbackground=[("readonly", colors["card"])],
            background=[("readonly", colors["card"])],
            foreground=[("disabled", colors["ink_soft"]), ("readonly", colors["ink"])],
        )

        style.configure(
            "Primary.TButton",
            padding=(13, 8),
            font=self.fonts["button"],
            foreground=colors["accent_text"],
            background=colors["accent"],
            borderwidth=1,
            bordercolor=colors["accent_deep"],
            focusthickness=0,
            relief="flat",
        )
        style.map(
            "Primary.TButton",
            background=[
                ("disabled", colors["accent_disabled"]),
                ("pressed", colors["accent_deep"]),
                ("active", colors["accent_hover"]),
            ],
        )

        style.configure(
            "Secondary.TButton",
            padding=(13, 8),
            font=self.fonts["button"],
            foreground=colors["secondary_text"],
            background=colors["secondary"],
            borderwidth=1,
            bordercolor=colors["secondary_deep"],
            focusthickness=0,
            relief="flat",
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("disabled", colors["secondary_disabled"]),
                ("pressed", colors["secondary_deep"]),
                ("active", colors["secondary_hover"]),
            ],
        )

        style.configure(
            "Ink.TButton",
            padding=(13, 8),
            font=self.fonts["button"],
            foreground=colors["paper"],
            background=colors["ink_button"],
            borderwidth=1,
            bordercolor=colors["ink_button_hover"],
            focusthickness=0,
            relief="flat",
        )
        style.map(
            "Ink.TButton",
            background=[
                ("disabled", colors["ink_button_disabled"]),
                ("pressed", colors["ink_button_hover"]),
                ("active", colors["ink_button_hover"]),
            ],
        )

        style.configure(
            "Neutral.TButton",
            padding=(13, 8),
            font=self.fonts["button"],
            foreground=colors["neutral_button_text"],
            background=colors["neutral_button"],
            borderwidth=1,
            bordercolor=colors["border_strong"],
            focusthickness=0,
            relief="flat",
        )
        style.map(
            "Neutral.TButton",
            background=[
                ("disabled", colors["neutral_button_disabled"]),
                ("pressed", colors["neutral_button_hover"]),
                ("active", colors["neutral_button_hover"]),
            ],
        )

        style.configure(
            "Card.TCheckbutton",
            background=colors["card"],
            foreground=colors["ink"],
            font=self.fonts["body"],
        )
        style.map(
            "Card.TCheckbutton",
            background=[("active", colors["card"]), ("disabled", colors["card"])],
            foreground=[("disabled", colors["ink_soft"]), ("!disabled", colors["ink"])],
        )

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        container = ttk.Frame(self.root, style="App.TFrame", padding=16)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=0, minsize=330)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(
            container, style="Panel.TFrame", padding=(16, 16, 16, 16), width=330
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)

        self.stage = ttk.Frame(
            container, style="Stage.TFrame", padding=(14, 12, 14, 14)
        )
        self.stage.grid(row=0, column=1, sticky="nsew")
        self.stage.columnconfigure(0, weight=1)
        self.stage.rowconfigure(1, weight=1)

        self._build_sidebar()
        self._build_stage()

    def _build_sidebar(self) -> None:
        accent_strip = tk.Frame(self.sidebar, bg=self.COLORS["accent"], height=6)
        accent_strip.grid(row=0, column=0, sticky="ew")

        brand = tk.Frame(
            self.sidebar, bg=self.COLORS["panel"], bd=0, highlightthickness=0
        )
        brand.grid(row=1, column=0, sticky="ew", padx=(4, 2), pady=(14, 14))
        brand.columnconfigure(0, weight=1)

        tk.Label(
            brand,
            text="CP Generator",
            bg=self.COLORS["panel"],
            fg=self.COLORS["ink"],
            font=self.fonts["hero"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        brand_copy = tk.Label(
            brand,
            text="Lightweight crease-pattern studio",
            bg=self.COLORS["panel"],
            fg=self.COLORS["ink_soft"],
            font=self.fonts["body"],
            justify="left",
            anchor="w",
            wraplength=264,
        )
        brand_copy.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._register_wrap_label(
            brand_copy, brand, padding=8, minimum=220, maximum=280
        )

        setup_card = self._make_card(self.sidebar)
        setup_card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        setup_card.columnconfigure(0, weight=1)

        ttk.Label(setup_card, text="Pattern Setup", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4)
        )
        ttk.Label(
            setup_card,
            text="Interior points",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=16)

        validate_cmd = (self.root.register(self._validate_point_count), "%P")
        self.point_entry = ttk.Entry(
            setup_card,
            textvariable=self.point_count_var,
            style="Modern.TEntry",
            justify="center",
            width=8,
            validate="key",
            validatecommand=validate_cmd,
            font=self.fonts["body"],
        )
        self.point_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 6))
        self.point_entry.bind("<Return>", lambda _event: self.make_cp())

        generate_button = ttk.Button(
            setup_card,
            text="Generate",
            command=self.make_cp,
            style="Primary.TButton",
        )
        generate_button.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 6))
        self._interactive_widgets.extend([self.point_entry, generate_button])

        self.labels_toggle = ttk.Checkbutton(
            setup_card,
            text="Vertex labels",
            variable=self.show_labels_var,
            command=self.redraw,
            style="Card.TCheckbutton",
        )
        self.labels_toggle.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 12))
        self._interactive_widgets.append(self.labels_toggle)

        actions_card = self._make_card(self.sidebar)
        actions_card.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        actions_card.columnconfigure(0, weight=1)

        ttk.Label(actions_card, text="Actions", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8)
        )

        optimize_button = ttk.Button(
            actions_card,
            text="Optimize",
            command=self.optimize_cp,
            style="Ink.TButton",
        )
        optimize_button.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        assign_button = ttk.Button(
            actions_card,
            text="Assign M/V",
            command=self.assign_mv,
            style="Secondary.TButton",
        )
        assign_button.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))

        export_button = ttk.Button(
            actions_card,
            text="Export",
            command=self.export_svg,
            style="Neutral.TButton",
        )
        export_button.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))

        save_button = ttk.Button(
            actions_card,
            text="Save",
            command=self.save_session,
            style="Neutral.TButton",
        )
        save_button.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))

        load_button = ttk.Button(
            actions_card,
            text="Load",
            command=self.load_session,
            style="Neutral.TButton",
        )
        load_button.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 12))

        sample_button = ttk.Button(
            actions_card,
            text="Box Head",
            command=self.load_box_head_sample,
            style="Neutral.TButton",
        )
        sample_button.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 12))

        self._interactive_widgets.extend(
            [
                optimize_button,
                assign_button,
                export_button,
                save_button,
                load_button,
                sample_button,
            ]
        )

        stats_card = self._make_card(self.sidebar)
        stats_card.grid(row=4, column=0, sticky="ew", pady=(0, 14))
        stats_card.columnconfigure(0, weight=1)
        stats_card.columnconfigure(1, weight=1)
        stats_card.columnconfigure(2, weight=1)

        ttk.Label(stats_card, text="Live Pattern Stats", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 8)
        )

        self._create_stat_chip(
            stats_card,
            row=1,
            column=0,
            value_var=self.vertex_count_var,
            label="Vertices",
            accent=self.COLORS["accent"],
        )
        self._create_stat_chip(
            stats_card,
            row=1,
            column=1,
            value_var=self.fold_count_var,
            label="Folds",
            accent=self.COLORS["secondary"],
        )
        self._create_stat_chip(
            stats_card,
            row=1,
            column=2,
            value_var=self.interior_count_var,
            label="Interior",
            accent=self.COLORS["ink_button"],
        )

        status_card = self._make_card(self.sidebar, background=self.COLORS["status_bg"])
        status_card.grid(row=5, column=0, sticky="nsew")
        status_card.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(5, weight=1)

        session_title = tk.Label(
            status_card,
            text="Session Status",
            bg=self.COLORS["status_bg"],
            fg=self.COLORS["ink"],
            font=self.fonts["section"],
        )
        session_title.grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))

        self.state_badge = tk.Label(
            status_card,
            textvariable=self.state_var,
            bg=self.BADGE_COLORS["neutral"][0],
            fg=self.BADGE_COLORS["neutral"][1],
            padx=10,
            pady=5,
            font=self.fonts["badge"],
        )
        self.state_badge.grid(row=1, column=0, sticky="w", padx=18)

        status_message = tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=self.COLORS["status_bg"],
            fg=self.COLORS["ink"],
            justify="left",
            anchor="nw",
            wraplength=252,
            font=self.fonts["body"],
        )
        status_message.grid(row=2, column=0, sticky="ew", padx=18, pady=(12, 0))
        self._register_wrap_label(status_message, status_card, padding=42, minimum=252)

        status_detail = tk.Label(
            status_card,
            textvariable=self.detail_var,
            bg=self.COLORS["status_bg"],
            fg=self.COLORS["status_detail"],
            justify="left",
            anchor="nw",
            wraplength=252,
            font=self.fonts["small"],
        )
        status_detail.grid(row=3, column=0, sticky="ew", padx=18, pady=(10, 18))
        self._register_wrap_label(status_detail, status_card, padding=42, minimum=252)

    def _build_stage(self) -> None:
        header = ttk.Frame(self.stage, style="Stage.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        ttk.Label(header, text="Crease Studio", style="StageTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        stage_copy = ttk.Label(
            header,
            text="Crease pattern and folded figure stay in view together, with direct 3D inspection on the right.",
            style="StageBody.TLabel",
            justify="left",
        )
        stage_copy.grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 12))
        self._register_wrap_label(
            stage_copy, header, padding=280, minimum=240, maximum=760
        )

        legend = tk.Frame(header, bg=self.COLORS["panel_alt"])
        legend.grid(row=0, column=1, rowspan=2, sticky="e")
        self._create_legend_item(legend, "Mountain", self.COLORS["mountain"]).grid(
            row=0, column=0, padx=(0, 10)
        )
        self._create_legend_item(legend, "Valley", self.COLORS["valley"]).grid(
            row=0, column=1, padx=(0, 10)
        )
        self._create_legend_item(
            legend, "Unassigned", self.COLORS["neutral_fold"]
        ).grid(row=0, column=2)

        views = ttk.Frame(self.stage, style="Stage.TFrame")
        views.grid(row=1, column=0, sticky="nsew")
        views.columnconfigure(0, weight=1, uniform="workspace")
        views.columnconfigure(1, weight=1, uniform="workspace")
        views.rowconfigure(0, weight=1)

        sheet_card = self._make_card(views, background=self.COLORS["card"])
        sheet_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        sheet_card.grid_columnconfigure(0, weight=1)
        sheet_card.grid_rowconfigure(1, weight=1)

        tk.Label(
            sheet_card,
            text="Crease Sheet",
            bg=self.COLORS["card"],
            fg=self.COLORS["ink"],
            font=self.fonts["card_title"],
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))

        sheet_shell = tk.Frame(
            sheet_card,
            bg=self.COLORS["card"],
            highlightthickness=1,
            highlightbackground=self.COLORS["border_strong"],
            bd=0,
        )
        sheet_shell.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 0))
        sheet_shell.grid_rowconfigure(0, weight=1)
        sheet_shell.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            sheet_shell,
            bg=self.COLORS["canvas_bg"],
            bd=0,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.canvas.bind("<Configure>", lambda _event: self._redraw_sheet())

        sheet_caption = ttk.Label(
            sheet_card,
            textvariable=self.sheet_caption_var,
            style="CardMuted.TLabel",
            justify="left",
        )
        sheet_caption.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 16))
        self._register_wrap_label(sheet_caption, sheet_card, padding=38, minimum=220)

        preview_card = self._make_card(views, background=self.COLORS["card"])
        preview_card.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        preview_card.grid_columnconfigure(0, weight=1)
        preview_card.grid_rowconfigure(1, weight=1)

        tk.Label(
            preview_card,
            text="Folded Figure",
            bg=self.COLORS["card"],
            fg=self.COLORS["ink"],
            font=self.fonts["card_title"],
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))

        preview_shell = tk.Frame(
            preview_card,
            bg=self.COLORS["card"],
            highlightthickness=1,
            highlightbackground=self.COLORS["border_strong"],
            bd=0,
        )
        preview_shell.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 0))
        preview_shell.grid_rowconfigure(0, weight=1)
        preview_shell.grid_columnconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(
            preview_shell,
            bg=self.COLORS["preview_bg"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.preview_canvas.bind("<Configure>", lambda _event: self._redraw_preview())
        self.preview_canvas.bind("<ButtonPress-1>", self._start_preview_drag)
        self.preview_canvas.bind("<B1-Motion>", self._drag_preview)
        self.preview_canvas.bind("<ButtonRelease-1>", self._end_preview_drag)
        self.preview_canvas.bind("<Double-Button-1>", self._reset_preview_camera)
        self.preview_canvas.bind("<MouseWheel>", self._zoom_preview)
        self.preview_canvas.bind("<Button-4>", self._zoom_preview)
        self.preview_canvas.bind("<Button-5>", self._zoom_preview)

        controls = tk.Frame(preview_card, bg=self.COLORS["card"])
        controls.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 8))
        controls.columnconfigure(2, weight=1)

        self.preview_play_button = ttk.Button(
            controls,
            textvariable=self.preview_button_var,
            command=self._toggle_preview_animation,
            style="Secondary.TButton",
        )
        self.preview_play_button.grid(row=0, column=0, sticky="w")

        self.preview_replay_button = ttk.Button(
            controls,
            text="Replay",
            command=lambda: self._replay_preview(play=True),
            style="Neutral.TButton",
        )
        self.preview_replay_button.grid(row=0, column=1, sticky="w", padx=(10, 10))

        self.preview_slider = ttk.Scale(
            controls,
            from_=0.0,
            to=1.0,
            variable=self.preview_progress_var,
            command=self._on_preview_progress,
        )
        self.preview_slider.grid(row=0, column=2, sticky="ew", padx=(0, 10))

        self.preview_progress_label = tk.Label(
            controls,
            textvariable=self.preview_progress_text_var,
            bg=self.COLORS["card"],
            fg=self.COLORS["ink_soft"],
            font=self.fonts["small"],
        )
        self.preview_progress_label.grid(row=0, column=3, sticky="e")

        preview_toggles = tk.Frame(preview_card, bg=self.COLORS["card"])
        preview_toggles.grid(row=3, column=0, sticky="ew", padx=16)
        preview_toggles.columnconfigure(0, weight=0)
        preview_toggles.columnconfigure(1, weight=1)

        self.preview_loop_toggle = ttk.Checkbutton(
            preview_toggles,
            text="Loop fold animation",
            variable=self.preview_loop_var,
            style="Card.TCheckbutton",
        )
        self.preview_loop_toggle.grid(row=0, column=0, sticky="w")

        self.preview_edge_families_toggle = ttk.Checkbutton(
            preview_toggles,
            text="Color cut-edge pairs",
            variable=self.preview_edge_families_var,
            command=self._redraw_preview,
            style="Card.TCheckbutton",
        )
        self.preview_edge_families_toggle.grid(
            row=0, column=1, sticky="w", padx=(16, 0)
        )

        preview_hint = ttk.Label(
            preview_card,
            text="Drag to orbit, Shift-drag to roll, scroll to zoom, double-click to reset. Cut-edge mode colors matching seam copies alike, including triangulated mesh cuts.",
            style="CardMuted.TLabel",
            justify="left",
        )
        preview_hint.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 0))
        self._register_wrap_label(preview_hint, preview_card, padding=38, minimum=220)

        preview_summary = ttk.Label(
            preview_card,
            textvariable=self.preview_summary_var,
            style="CardMuted.TLabel",
            justify="left",
        )
        preview_summary.grid(row=5, column=0, sticky="ew", padx=16, pady=(10, 16))
        self._register_wrap_label(
            preview_summary, preview_card, padding=38, minimum=220
        )

        self._interactive_widgets.extend(
            [
                self.preview_play_button,
                self.preview_replay_button,
                self.preview_slider,
                self.preview_loop_toggle,
                self.preview_edge_families_toggle,
            ]
        )
        self._preview_widgets.extend(
            [
                self.preview_play_button,
                self.preview_replay_button,
                self.preview_slider,
                self.preview_loop_toggle,
                self.preview_edge_families_toggle,
            ]
        )

    def _make_card(self, parent: tk.Widget, background: str | None = None) -> tk.Frame:
        bg = background or self.COLORS["card"]
        return tk.Frame(
            parent,
            bg=bg,
            highlightthickness=1,
            highlightbackground=self.COLORS["border_strong"],
            bd=0,
        )

    def _create_stat_chip(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        value_var: tk.StringVar,
        label: str,
        accent: str,
    ) -> None:
        chip = tk.Frame(parent, bg=self.COLORS["card"], bd=0)
        chip.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(16 if column == 0 else 8, 0),
            pady=(0, 10),
        )
        chip.grid_columnconfigure(0, weight=1)

        tk.Frame(chip, bg=accent, height=3).grid(
            row=0, column=0, sticky="ew", pady=(0, 8)
        )
        tk.Label(
            chip,
            text=label,
            bg=self.COLORS["card"],
            fg=self.COLORS["ink_soft"],
            font=self.fonts["small"],
        ).grid(row=1, column=0, sticky="w")
        tk.Label(
            chip,
            textvariable=value_var,
            bg=self.COLORS["card"],
            fg=self.COLORS["ink"],
            font=self.fonts["stat_value"],
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

    def _create_legend_item(self, parent: tk.Widget, text: str, color: str) -> tk.Frame:
        item = tk.Frame(parent, bg=self.COLORS["panel_alt"])
        swatch = tk.Canvas(
            item,
            width=18,
            height=18,
            bg=self.COLORS["panel_alt"],
            highlightthickness=0,
            bd=0,
        )
        swatch.grid(row=0, column=0, padx=(0, 6))
        swatch.create_line(2, 9, 16, 9, fill=color, width=3, capstyle=tk.ROUND)
        tk.Label(
            item,
            text=text,
            bg=self.COLORS["panel_alt"],
            fg=self.COLORS["ink_soft"],
            font=self.fonts["small"],
        ).grid(row=0, column=1)
        return item

    def _handle_close(self) -> None:
        self._closing = True
        self._stop_preview_animation()
        if self._wrap_refresh_job is not None:
            self.root.after_cancel(self._wrap_refresh_job)
            self._wrap_refresh_job = None
        self.root.destroy()

    def _register_wrap_label(
        self,
        widget: tk.Widget,
        parent: tk.Widget,
        padding: int,
        minimum: int,
        maximum: int | None = None,
    ) -> None:
        self._wrap_labels.append((widget, parent, padding, minimum, maximum))

    def _queue_wrap_refresh(self, _event: tk.Event | None = None) -> None:
        if self._closing:
            return
        if self._wrap_refresh_job is not None:
            self.root.after_cancel(self._wrap_refresh_job)
        self._wrap_refresh_job = self.root.after_idle(self._refresh_wrap_lengths)

    def _refresh_wrap_lengths(self) -> None:
        if self._closing:
            self._wrap_refresh_job = None
            return
        self._wrap_refresh_job = None
        for widget, parent, padding, minimum, maximum in self._wrap_labels:
            if not widget.winfo_exists() or not parent.winfo_exists():
                continue
            width = max(parent.winfo_width() - padding, minimum)
            if maximum is not None:
                width = min(width, maximum)
            try:
                widget.configure(wraplength=width)
            except tk.TclError:
                continue

    def _refresh_preview_summary(self, *_args) -> None:
        caption = self.preview_caption_var.get().strip()
        detail = self.preview_detail_var.get().strip()
        if caption and detail:
            self.preview_summary_var.set(f"{caption} {detail}")
        elif caption:
            self.preview_summary_var.set(caption)
        else:
            self.preview_summary_var.set(detail)

    def _validate_point_count(self, proposed: str) -> bool:
        return proposed == "" or proposed.isdigit()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self._stop_preview_animation()

        state = ["disabled"] if busy else ["!disabled"]
        for widget in self._interactive_widgets:
            widget.state(state)

        if not busy:
            self._sync_preview_controls()

        cursor = "watch" if busy else ""
        self.root.configure(cursor=cursor)
        self.canvas.configure(cursor="watch" if busy else "crosshair")
        self.preview_canvas.configure(cursor="watch" if busy else "hand2")
        self.root.update_idletasks()

    def _set_status(self, state: str, message: str, detail: str, tone: str) -> None:
        badge_bg, badge_fg = self.BADGE_COLORS.get(tone, self.BADGE_COLORS["neutral"])
        self.state_var.set(state)
        self.status_var.set(message)
        self.detail_var.set(detail)
        self.state_badge.configure(bg=badge_bg, fg=badge_fg)

    def _update_stats(self) -> None:
        self.vertex_count_var.set(str(len(self.pattern.vertices)))
        self.fold_count_var.set(str(len(self.pattern.folds)))
        self.interior_count_var.set(str(len(self.pattern.none_edge_vertices())))

    def _parse_point_count(self) -> int | None:
        raw = self.point_count_var.get().strip()
        if not raw:
            self._set_status(
                "Input Needed",
                "Enter how many random interior points to generate.",
                "Use a non-negative whole number, then generate a new pattern.",
                tone="warning",
            )
            return None

        count = int(raw)
        if count < 0:
            self._set_status(
                "Input Needed",
                "Point count cannot be negative.",
                "Use zero or a positive whole number instead.",
                tone="warning",
            )
            return None
        return count

    def _build_pattern(self, point_count: int) -> cp.CreasePattern:
        pattern = cp.CreasePattern()
        pattern.side = MODEL_SIDE
        pattern.add_square_vertices()
        for _ in range(point_count):
            pattern.add_random_vertex()
        pattern.push_to_edge(20)
        pattern.triangulate()
        pattern.evenize_vertices()
        pattern.remove_edge_folds()
        return pattern

    def _run_action(self, busy_message: str, action) -> None:
        self._set_busy(True)
        self._set_status(
            "Working",
            busy_message,
            "The sheet and folded figure will refresh as soon as the operation completes.",
            tone="working",
        )
        try:
            action()
        except Exception as exc:
            self._set_status(
                "Error",
                f"Operation failed: {exc}",
                "The previous pattern remains available. Try a smaller point count if the geometry is unstable.",
                tone="danger",
            )
        finally:
            self._set_busy(False)

    def _clear_fold_assignments(self) -> None:
        for fold in self.pattern.folds:
            fold.type = -1

    def _clone_pattern(self, pattern: cp.CreasePattern) -> cp.CreasePattern:
        return pattern.clone()

    def _edge_map(self, pattern: cp.CreasePattern) -> dict[tuple[int, int], cp.Fold]:
        vertex_index = {vertex: index for index, vertex in enumerate(pattern.vertices)}
        return {
            tuple(sorted((vertex_index[fold.v1], vertex_index[fold.v2]))): fold
            for fold in pattern.folds
        }

    def _same_connectivity(
        self, first: cp.CreasePattern, second: cp.CreasePattern
    ) -> bool:
        if len(first.vertices) != len(second.vertices):
            return False
        if len(first.folds) != len(second.folds):
            return False
        return set(self._edge_map(first)) == set(self._edge_map(second))

    def _copy_fold_types(
        self, source: cp.CreasePattern, target: cp.CreasePattern
    ) -> bool:
        if not self._same_connectivity(source, target):
            return False

        source_edges = self._edge_map(source)
        target_edges = self._edge_map(target)
        for edge_key, target_fold in target_edges.items():
            target_fold.type = source_edges[edge_key].type
        return True

    def _refresh_preview_reference(self) -> None:
        if self.sample_key == box_head_sample.BOX_HEAD_KEY:
            self.preview_reference_pattern = self._clone_pattern(self.pattern)
            return
        if not self.pattern.folds:
            return
        candidate = self._clone_pattern(self.pattern)
        try:
            fold_sim.build_folded_figure(candidate)
        except fold_sim.FoldSimulationError:
            return
        self.preview_reference_pattern = candidate

    def _rebuild_preview(self, autoplay: bool = False) -> None:
        self._stop_preview_animation()
        self.preview_progress_var.set(0.0)
        self._update_preview_progress_text()

        if self.sample_key == box_head_sample.BOX_HEAD_KEY:
            self.preview_model = fold_sim.build_box_head_figure(self.pattern)
            self.preview_caption_var.set(
                "The Box Head sample is folding from the authored crease pattern."
            )
            self.preview_detail_var.set(
                "The animation now follows the existing fold solver first, then settles into a Box Head-specific shaped finish so the sample stays seamless and still reads like the reference character."
            )
            self._sync_preview_controls()
            self._redraw_preview()
            if autoplay:
                self._replay_preview(play=True)
            return

        if not self.pattern.vertices:
            self.preview_model = None
            self.preview_caption_var.set(
                "Generate a crease pattern to open the folded figure."
            )
            self.preview_detail_var.set(
                "The 3D simulation appears here after the sheet exists and a fold assignment is ready."
            )
            self._sync_preview_controls()
            self._redraw_preview()
            return

        if not self.pattern.folds:
            self.preview_model = None
            self.preview_caption_var.set("This sheet has no interior folds to animate.")
            self.preview_detail_var.set(
                "Generate a denser pattern if you want a folded figure with internal structure."
            )
            self._sync_preview_controls()
            self._redraw_preview()
            return

        if not self.fold_assignment_ready:
            self.preview_model = None
            self.preview_caption_var.set(
                "Assign mountain and valley folds to unlock the folded figure."
            )
            self.preview_detail_var.set(
                "The 3D preview waits for a valid fold assignment so the final stack is not misleading."
            )
            self._sync_preview_controls()
            self._redraw_preview()
            return

        failure_messages: list[str] = []
        candidates: list[tuple[str, str, cp.CreasePattern]] = [
            ("exact", "current", self._clone_pattern(self.pattern))
        ]
        if self.preview_reference_pattern is not None:
            fallback = self._clone_pattern(self.preview_reference_pattern)
            if self._copy_fold_types(self.pattern, fallback):
                candidates.append(("exact", "reference", fallback))

        candidates.append(("mesh", "current", self._clone_pattern(self.pattern)))
        if self.preview_reference_pattern is not None:
            fallback = self._clone_pattern(self.preview_reference_pattern)
            if self._copy_fold_types(self.pattern, fallback):
                candidates.append(("mesh", "reference", fallback))

        for solver_name, source_name, candidate in candidates:
            try:
                if solver_name == "exact":
                    model = fold_sim.build_folded_figure(candidate)
                else:
                    model = fold_sim.build_approximate_folded_figure_with_mode(
                        candidate, spatial_mode=False
                    )
            except fold_sim.FoldSimulationError as exc:
                failure_messages.append(str(exc))
                continue

            self.preview_model = model
            if source_name == "current" and solver_name == "exact":
                self.preview_reference_pattern = self._clone_pattern(candidate)
                notes: list[str] = []
                if model.uses_provisional_signs:
                    notes.append(
                        "A few underdetermined creases were oriented automatically."
                    )
                if model.uses_approximate_cycles:
                    notes.append(
                        f"The solver detected mild cycle drift ({model.cycle_drift:.3f}), so the final stack is an approximation."
                    )

                if notes:
                    self.preview_caption_var.set(
                        "The folded figure is ready with a few guarded approximations."
                    )
                    self.preview_detail_var.set(" ".join(notes))
                else:
                    self.preview_caption_var.set(
                        "The folded figure is ready and reflects the current crease geometry."
                    )
                    self.preview_detail_var.set(
                        "Press play to fold, or drag directly on the model to inspect the final layered state from any angle."
                    )
            elif source_name == "reference" and solver_name == "exact":
                self.preview_caption_var.set(
                    "The folded figure is ready from the last stable planar geometry."
                )
                detail = "The live optimized sheet drifted into a numerically unstable layout, so the preview falls back to the last geometry that remained planar and flat-foldable enough to stack."
                if model.uses_provisional_signs:
                    detail += (
                        " A few underdetermined creases were oriented automatically."
                    )
                if model.uses_approximate_cycles:
                    detail += f" Cycle drift remained at about {model.cycle_drift:.3f}, so the stack is approximate."
                self.preview_detail_var.set(detail)
            elif source_name == "current":
                self.preview_caption_var.set(
                    "The folded figure is ready with a mesh-based 3D fallback."
                )
                detail = "The exact face solver rejected this sheet, so the preview now uses a guarded triangle mesh that still settles into a flat layered stack."
                if model.uses_provisional_signs:
                    detail += (
                        " A few underdetermined creases were oriented automatically."
                    )
                self.preview_detail_var.set(detail)
            else:
                self.preview_caption_var.set(
                    "The folded figure is ready from a stable mesh fallback."
                )
                detail = "The current geometry became too unstable for exact reconstruction, so the preview uses a fallback mesh from the last stable sheet and still closes into a flat layered stack."
                if model.uses_provisional_signs:
                    detail += (
                        " A few underdetermined creases were oriented automatically."
                    )
                self.preview_detail_var.set(detail)

            self._sync_preview_controls()
            self._redraw_preview()
            if autoplay:
                self._replay_preview(play=True)
            return

        self.preview_model = None
        failure = (
            failure_messages[-1]
            if failure_messages
            else "The folded figure could not be constructed."
        )
        self.preview_caption_var.set("The folded figure is unavailable for this sheet.")
        self.preview_detail_var.set(failure)
        self._sync_preview_controls()
        self._redraw_preview()

    def _sync_preview_controls(self) -> None:
        enabled = (not self._busy) and (self.preview_model is not None)
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in self._preview_widgets:
            widget.state(state)

        if not enabled:
            self.preview_button_var.set("Play Fold")

    def _update_preview_progress_text(self) -> None:
        progress = round(self.preview_progress_var.get() * 100)
        self.preview_progress_text_var.set(f"Fold {progress}%")

    def _toggle_preview_animation(self) -> None:
        if self.preview_model is None:
            return

        if self._preview_job is not None:
            self._stop_preview_animation()
            return

        if self.preview_progress_var.get() >= 0.999:
            self.preview_progress_var.set(0.0)

        self._preview_direction = 1
        self.preview_button_var.set("Pause")
        self._advance_preview()

    def _stop_preview_animation(self) -> None:
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
            self._preview_job = None
        self.preview_button_var.set("Play Fold")

    def _replay_preview(self, play: bool = True) -> None:
        self._stop_preview_animation()
        self.preview_progress_var.set(0.0)
        self._update_preview_progress_text()
        self._redraw_preview()
        if play and self.preview_model is not None:
            self._toggle_preview_animation()

    def _advance_preview(self) -> None:
        self._preview_job = None
        if self.preview_model is None:
            self.preview_button_var.set("Play Fold")
            return

        progress = self.preview_progress_var.get() + 0.022 * self._preview_direction

        if progress >= 1.0:
            progress = 1.0
            if self.preview_loop_var.get():
                self._preview_direction = -1
            else:
                self.preview_progress_var.set(progress)
                self._update_preview_progress_text()
                self._redraw_preview()
                self.preview_button_var.set("Play Fold")
                return

        if progress <= 0.0:
            progress = 0.0
            if self.preview_loop_var.get():
                self._preview_direction = 1
            else:
                self.preview_progress_var.set(progress)
                self._update_preview_progress_text()
                self._redraw_preview()
                self.preview_button_var.set("Play Fold")
                return

        self.preview_progress_var.set(progress)
        self._update_preview_progress_text()
        self._redraw_preview()
        self._preview_job = self.root.after(24, self._advance_preview)

    def _on_preview_progress(self, value: str) -> None:
        if self.preview_model is None:
            return

        if self._preview_job is not None:
            self._stop_preview_animation()

        try:
            self.preview_progress_var.set(float(value))
        except ValueError:
            return
        self._update_preview_progress_text()
        self._redraw_preview()

    def _start_preview_drag(self, event: tk.Event) -> None:
        if self._busy:
            return
        self._preview_drag_last = (int(event.x), int(event.y))
        self.preview_canvas.configure(cursor="fleur")

    def _drag_preview(self, event: tk.Event) -> None:
        if self._preview_drag_last is None:
            return
        last_x, last_y = self._preview_drag_last
        dx = int(event.x) - last_x
        dy = int(event.y) - last_y
        self._preview_drag_last = (int(event.x), int(event.y))

        if event.state & 0x0001:
            self._preview_orbit_roll += dx * 0.012
        else:
            self._preview_orbit_yaw += dx * 0.014
            self._preview_orbit_pitch -= dy * 0.014
            pitch_limit = math.radians(88)
            self._preview_orbit_pitch = max(
                min(self._preview_orbit_pitch, pitch_limit), -pitch_limit
            )

        self._redraw_preview()

    def _end_preview_drag(self, _event: tk.Event | None = None) -> None:
        self._preview_drag_last = None
        if not self._busy:
            self.preview_canvas.configure(cursor="hand2")

    def _reset_preview_camera(self, _event: tk.Event | None = None) -> None:
        self._preview_orbit_yaw = 0.0
        self._preview_orbit_pitch = 0.0
        self._preview_orbit_roll = 0.0
        self._preview_zoom = 1.0
        self._redraw_preview()

    def _zoom_preview(self, event: tk.Event) -> None:
        if self._busy:
            return
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = 1 if event.delta > 0 else -1
        elif getattr(event, "num", None) == 4:
            delta = 1
        elif getattr(event, "num", None) == 5:
            delta = -1
        if delta == 0:
            return
        factor = 1.08 if delta > 0 else 1 / 1.08
        self._preview_zoom = min(max(self._preview_zoom * factor, 0.6), 2.4)
        self._redraw_preview()

    def make_cp(self, initial: bool = False) -> None:
        point_count = self._parse_point_count()
        if point_count is None:
            return

        def action() -> None:
            self.pattern = self._build_pattern(point_count)
            self.sample_key = None
            self.preview_reference_pattern = self._clone_pattern(self.pattern)
            self.fold_assignment_ready = False
            self.preview_model = None
            self._reset_preview_camera()
            self._update_stats()
            self.sheet_caption_var.set(
                "Resize the window to inspect the sheet at any scale. Optimize next if you want cleaner flat-fold geometry."
            )
            detail = "Optimize the geometry before assigning folds for the best chance of a valid mountain and valley pattern."
            title = (
                f"Generated a crease pattern with {point_count} random interior points."
            )
            if initial:
                detail = "Use the controls on the left to regenerate, refine, fold, and export this sheet."
            self._set_status(
                "Fresh",
                title,
                detail,
                tone="neutral",
            )
            self._rebuild_preview()
            self.redraw()

        self._run_action("Generating a new crease pattern...", action)

    def optimize_cp(self) -> None:
        if not self.pattern.vertices:
            self._set_status(
                "No Pattern",
                "Generate a crease pattern before optimizing it.",
                "The optimizer needs an active sheet.",
                tone="warning",
            )
            return

        if self.sample_key == box_head_sample.BOX_HEAD_KEY:
            self._set_status(
                "Locked",
                "The Box Head sample already uses authored 16x16 geometry.",
                "Optimization is skipped so the published grid and the dedicated folded preview stay aligned.",
                tone="neutral",
            )
            return

        def action() -> None:
            res = self.pattern.optimize()
            self._clear_fold_assignments()
            self.fold_assignment_ready = False
            self.preview_model = None
            self._refresh_preview_reference()
            self._update_stats()
            self._rebuild_preview()
            self.redraw()
            if res.success:
                self.sheet_caption_var.set(
                    "Optimization refreshed the geometry. Reassign folds next to recolor the sheet and reopen the folded figure."
                )
                self._set_status(
                    "Optimized",
                    "Geometry optimization converged successfully.",
                    "Any previous mountain and valley assignment was cleared because the sheet geometry changed.",
                    tone="success",
                )
            else:
                self.sheet_caption_var.set(
                    "Optimization changed the sheet but did not converge cleanly. Reassign folds only if the geometry still looks plausible."
                )
                self._set_status(
                    "Needs Work",
                    "Optimization finished without convergence.",
                    "The assignment was cleared because the geometry changed. Try optimizing again or regenerate a simpler pattern.",
                    tone="warning",
                )

        self._run_action("Optimizing crease geometry...", action)

    def assign_mv(self) -> None:
        if not self.pattern.vertices:
            self._set_status(
                "No Pattern",
                "Generate a crease pattern before assigning folds.",
                "Fold assignment works on the current sheet geometry.",
                tone="warning",
            )
            return

        if self.sample_key == box_head_sample.BOX_HEAD_KEY:
            self.fold_assignment_ready = True
            self.sheet_caption_var.set(
                "This authored 16x16 sample already carries mountain and valley assignments from the published crease pattern."
            )
            self._set_status(
                "Assigned",
                "The Box Head sample is already assigned and ready to animate.",
                "Press play on the right to inspect the dedicated folded character from any angle.",
                tone="success",
            )
            self._refresh_preview_reference()
            self._update_stats()
            self._rebuild_preview(autoplay=True)
            self.redraw()
            return

        def action() -> None:
            res = self.pattern.assign_mv()
            if res == []:
                self._clear_fold_assignments()
                self.fold_assignment_ready = False
                self.sheet_caption_var.set(
                    "This sheet stayed in neutral graphite because no valid mountain and valley assignment was found."
                )
                self._set_status(
                    "No Solution",
                    "No valid mountain and valley assignment was found for this geometry.",
                    "Try optimizing again or generate a different crease pattern.",
                    tone="danger",
                )
            else:
                self.fold_assignment_ready = True
                self.sheet_caption_var.set(
                    "Terracotta mountains and blue valleys are now assigned across the sheet."
                )
                detail = "The folded figure on the right can now animate into its layered final state."
                self._set_status(
                    "Assigned",
                    "Mountain and valley folds were assigned successfully.",
                    detail,
                    tone="success",
                )
            self._refresh_preview_reference()
            self._update_stats()
            self._rebuild_preview(autoplay=self.fold_assignment_ready)
            self.redraw()

        self._run_action("Assigning mountain and valley folds...", action)

    def export_svg(self) -> None:
        if not self.pattern.vertices:
            self._set_status(
                "No Pattern",
                "Generate a crease pattern before exporting it.",
                "Export writes both an SVG and a matching PNG.",
                tone="warning",
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Export crease pattern",
            defaultextension=".svg",
            filetypes=[("SVG files", "*.svg")],
            initialfile="crease_pattern.svg",
        )
        if not filename:
            self._set_status(
                "Export Canceled",
                "Export was canceled before any files were written.",
                "Choose a destination when you are ready to save the pattern.",
                tone="neutral",
            )
            return

        export_path = Path(filename)

        def action() -> None:
            self.pattern.export_svg(str(export_path))
            png_path = export_path.with_suffix(".png")
            self._update_stats()
            self.redraw()
            self.sheet_caption_var.set(
                "Vector lines are saved to SVG, and a matching PNG preview is written beside it."
            )
            self._set_status(
                "Exported",
                f"Saved {export_path.name} and {png_path.name}.",
                f"Files were written to {export_path.parent}.",
                tone="success",
            )

        self._run_action("Exporting crease pattern...", action)

    def save_session(self) -> None:
        if not self.pattern.vertices:
            self._set_status(
                "No Pattern",
                "Generate a crease pattern before saving a session.",
                "A session file stores the current sheet, fold assignments, and preview-ready state.",
                tone="warning",
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Save fold session",
            defaultextension=".cpfold.json",
            filetypes=[
                ("Crease pattern session", "*.cpfold.json"),
                ("JSON files", "*.json"),
            ],
            initialfile="fold_session.cpfold.json",
        )
        if not filename:
            self._set_status(
                "Save Canceled",
                "Save was canceled before any files were written.",
                "Choose a destination when you want to persist the current fold state.",
                tone="neutral",
            )
            return

        save_path = Path(filename)

        def action() -> None:
            payload = self._session_data()
            save_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._set_status(
                "Saved",
                f"Saved {save_path.name}.",
                f"The session can be loaded later to restore the current sheet and fold state from {save_path.parent}.",
                tone="success",
            )

        self._run_action("Saving session data...", action)

    def load_session(self) -> None:
        filename = filedialog.askopenfilename(
            title="Load fold session",
            filetypes=[
                ("Crease pattern session", "*.cpfold.json"),
                ("JSON files", "*.json"),
            ],
        )
        if not filename:
            self._set_status(
                "Load Canceled",
                "Load was canceled before any session was restored.",
                "Choose a saved session file when you want to continue a previous fold.",
                tone="neutral",
            )
            return

        load_path = Path(filename)

        def action() -> None:
            payload = json.loads(load_path.read_text(encoding="utf-8"))
            self._restore_session_data(payload)
            self._set_status(
                "Loaded",
                f"Loaded {load_path.name}.",
                "The crease sheet, fold assignment, and folded preview were restored from disk.",
                tone="success",
            )

        self._run_action("Loading session data...", action)

    def load_box_head_sample(self) -> None:
        def action() -> None:
            self.pattern = box_head_sample.build_box_head_pattern()
            self.sample_key = box_head_sample.BOX_HEAD_KEY
            self.preview_reference_pattern = self._clone_pattern(self.pattern)
            self.fold_assignment_ready = True
            self.preview_model = None
            self.point_count_var.set("16")
            self._reset_preview_camera()
            self._update_stats()
            self.sheet_caption_var.set(
                "This is an authored 16x16 Box Head crease pattern sample with fixed mountain and valley assignments."
            )
            self._set_status(
                "Loaded",
                "Loaded the Box Head 16x16 sample.",
                "The right panel now uses a dedicated folded character preview based on the published design page and tutorial reference.",
                tone="success",
            )
            self._rebuild_preview(autoplay=True)
            self.redraw()

        self._run_action("Loading Box Head sample...", action)

    def _session_data(self) -> dict[str, object]:
        return {
            "format": "cp-generator-session",
            "version": 1,
            "sample_key": self.sample_key,
            "point_count": self.point_count_var.get(),
            "show_labels": bool(self.show_labels_var.get()),
            "preview_loop": bool(self.preview_loop_var.get()),
            "preview_edge_families": bool(self.preview_edge_families_var.get()),
            "fold_assignment_ready": bool(self.fold_assignment_ready),
            "pattern": self.pattern.to_data(),
            "preview_reference_pattern": (
                self.preview_reference_pattern.to_data()
                if self.preview_reference_pattern is not None
                else None
            ),
        }

    def _restore_session_data(self, payload: dict[str, object]) -> None:
        if payload.get("format") != "cp-generator-session":
            raise ValueError("Unsupported session file format.")
        if payload.get("version") != 1:
            raise ValueError("Unsupported session file version.")

        pattern_data = payload.get("pattern")
        if not isinstance(pattern_data, dict):
            raise ValueError("Session file is missing crease-pattern data.")

        preview_reference_data = payload.get("preview_reference_pattern")
        self.pattern = cp.CreasePattern.from_data(pattern_data)
        sample_key = payload.get("sample_key")
        self.sample_key = str(sample_key) if isinstance(sample_key, str) else None
        self.preview_reference_pattern = (
            cp.CreasePattern.from_data(preview_reference_data)
            if isinstance(preview_reference_data, dict)
            else self._clone_pattern(self.pattern)
        )
        self.point_count_var.set(str(payload.get("point_count", DEFAULT_POINTS)))
        self.show_labels_var.set(bool(payload.get("show_labels", False)))
        self.preview_loop_var.set(bool(payload.get("preview_loop", True)))
        self.preview_edge_families_var.set(
            bool(payload.get("preview_edge_families", False))
        )
        self.fold_assignment_ready = bool(payload.get("fold_assignment_ready", False))
        self.preview_model = None
        self.preview_progress_var.set(0.0)
        self._reset_preview_camera()
        self._update_stats()
        self.sheet_caption_var.set(
            "This sheet was restored from a saved session. Optimize again only if you want to alter the loaded geometry."
        )

        assigned_folds = any(fold.type in (0, 1) for fold in self.pattern.folds)
        if not assigned_folds:
            self.fold_assignment_ready = False

        self._rebuild_preview()
        self.redraw()

    def redraw(self) -> None:
        self._redraw_sheet()
        self._redraw_preview()

    def _redraw_sheet(self) -> None:
        canvas = self.canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        colors = self.COLORS

        canvas.create_rectangle(
            0, 0, width, height, fill=colors["canvas_bg"], outline=""
        )

        if not self.pattern.vertices:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Generate a crease pattern to begin.",
                fill=colors["ink_soft"],
                font=self.fonts["stage_body"],
            )
            return

        margin = max(min(width, height) * 0.08, 42)
        sheet_size = min(width - 2 * margin, height - 2 * margin)
        if sheet_size <= 0:
            return

        left = (width - sheet_size) / 2
        top = (height - sheet_size) / 2
        right = left + sheet_size
        bottom = top + sheet_size

        canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            fill=colors["paper"],
            outline=colors["square_outline"],
            width=2,
        )
        canvas.create_rectangle(
            left + 8,
            top + 8,
            right - 8,
            bottom - 8,
            outline=colors["wash_one"],
            width=1,
        )

        for step in range(1, 10):
            x = left + (sheet_size * step / 10)
            y = top + (sheet_size * step / 10)
            canvas.create_line(x, top, x, bottom, fill=colors["grid"], width=1)
            canvas.create_line(left, y, right, y, fill=colors["grid"], width=1)

        side = self.pattern.side or 1
        if side == 0:
            side = 1

        def project(vertex: cp.Vertex) -> tuple[float, float]:
            return (
                left + (vertex.x / side) * sheet_size,
                top + (vertex.y / side) * sheet_size,
            )

        for fold in sorted(self.pattern.folds, key=lambda item: item.type):
            x1, y1 = project(fold.v1)
            x2, y2 = project(fold.v2)
            color = self._fold_color(fold.type)
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=colors["paper"],
                width=4.2,
                capstyle=tk.ROUND,
            )
            canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=color,
                width=2.2,
                capstyle=tk.ROUND,
            )

        show_labels = self.show_labels_var.get()
        for index, vertex in enumerate(self.pattern.vertices):
            x, y = project(vertex)
            is_edge = self.pattern.on_edge(vertex)
            outer_radius = 4 if is_edge else 3.3
            inner_radius = 2.1 if is_edge else 1.8

            canvas.create_oval(
                x - outer_radius,
                y - outer_radius,
                x + outer_radius,
                y + outer_radius,
                fill=colors["vertex_edge"],
                outline=colors["square_outline"],
            )
            canvas.create_oval(
                x - inner_radius,
                y - inner_radius,
                x + inner_radius,
                y + inner_radius,
                fill=colors["vertex_fill"],
                outline="",
            )

            if show_labels:
                self._draw_vertex_label(index, vertex, x, y, side)

    def _redraw_preview(self) -> None:
        canvas = self.preview_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        colors = self.COLORS

        canvas.create_rectangle(
            0, 0, width, height, fill=colors["preview_bg"], outline=""
        )

        if self.preview_model is None:
            canvas.create_text(
                width / 2,
                height * 0.44,
                text="Folded figure preview",
                fill=colors["ink"],
                font=self.fonts["preview_hero"],
            )
            canvas.create_text(
                width / 2,
                height * 0.56,
                text=self.preview_caption_var.get(),
                fill=colors["ink_soft"],
                width=width * 0.72,
                justify="center",
                font=self.fonts["body"],
            )
            return

        states = self.preview_model.frame(self.preview_progress_var.get())
        if not states:
            return

        current_centroid = np.concatenate(
            [state.points for state in states], axis=0
        ).mean(axis=0)
        world_states = [state.points - current_centroid for state in states]
        view_rotation = self._preview_view_rotation()
        light_direction = np.array([-0.32, -0.58, 0.75], dtype=float)
        light_direction /= np.linalg.norm(light_direction)

        view_states = [points @ view_rotation.T for points in world_states]
        all_view_points = np.concatenate(view_states, axis=0)
        span = float(
            max(np.ptp(all_view_points[:, 0]), np.ptp(all_view_points[:, 1]), 1.0)
        )
        camera_distance = span * 4.4

        projected_states = []
        all_projected = []
        for points in view_states:
            projected = []
            for x, y, z in points:
                factor = camera_distance / max(camera_distance - z, 0.25)
                projected.append((x * factor, y * factor, z))
            projected_states.append(projected)
            all_projected.extend(projected)

        projected_xy = np.array(
            [[point[0], point[1]] for point in all_projected], dtype=float
        )
        margin = max(min(width, height) * 0.10, 34)
        span_x = max(float(np.ptp(projected_xy[:, 0])), 1.0)
        span_y = max(float(np.ptp(projected_xy[:, 1])), 1.0)
        scale = self._preview_zoom * min(
            (width - 2 * margin) / span_x, (height - 2 * margin) / span_y
        )
        center_x = float(projected_xy[:, 0].mean())
        center_y = float(projected_xy[:, 1].mean())

        def to_screen(point: tuple[float, float, float]) -> tuple[float, float]:
            x = (point[0] - center_x) * scale + width / 2
            y = (point[1] - center_y) * scale + height / 2
            return x, y

        screen_states: list[list[tuple[float, float]]] = []
        for points in projected_states:
            screen_states.append([to_screen(point) for point in points])

        triangles_to_draw: list[tuple[float, list[float], str]] = []
        edge_segments: dict[
            tuple[int, int],
            tuple[float, tuple[float, float], tuple[float, float], str, float],
        ] = {}
        edge_occurrences: dict[
            tuple[int, int],
            list[tuple[str, float, tuple[float, float], tuple[float, float], float]],
        ] = {}
        camera_normal = np.array([0.0, 0.0, 1.0], dtype=float)
        color_edge_families = bool(self.preview_edge_families_var.get())

        for face_index, state in enumerate(states):
            view_points = view_states[face_index]
            screen_points = screen_states[face_index]

            normal = self._polygon_normal(view_points)
            if np.linalg.norm(normal) <= 1e-8:
                continue
            normal = normal / np.linalg.norm(normal)
            facing_camera = float(np.dot(normal, camera_normal))
            brightness = 0.72 + 0.28 * max(
                float(np.dot(normal, light_direction)), -0.25
            )
            base_color = (
                colors["preview_surface"]
                if facing_camera >= 0
                else colors["preview_back"]
            )
            fill_color = self._shade_color(base_color, brightness)

            for triangle in state.triangles:
                triangle_points = [screen_points[index] for index in triangle]
                triangle_depth = float(
                    np.mean([view_points[index][2] for index in triangle])
                )
                flat_points = [coord for point in triangle_points for coord in point]
                triangles_to_draw.append((triangle_depth, flat_points, fill_color))

            face_edge_keys = getattr(self.preview_model, "face_edge_keys", ())
            edge_render_kind = getattr(self.preview_model, "edge_render_kind", {})
            if face_index < len(face_edge_keys):
                for local_index, edge_key in enumerate(face_edge_keys[face_index]):
                    edge_kind = edge_render_kind.get(edge_key)
                    if edge_kind not in (fold_sim.BOUNDARY, fold_sim.FOLD, "mesh"):
                        continue
                    next_index = (local_index + 1) % len(screen_points)
                    line_depth = float(
                        (view_points[local_index][2] + view_points[next_index][2]) * 0.5
                    )
                    edge_occurrences.setdefault(edge_key, []).append(
                        (
                            edge_kind,
                            line_depth,
                            screen_points[local_index],
                            screen_points[next_index],
                            brightness,
                        )
                    )

        for _, flat_points, fill_color in sorted(
            triangles_to_draw, key=lambda item: item[0]
        ):
            canvas.create_polygon(
                *flat_points,
                fill=fill_color,
                outline=fill_color,
                width=1.0,
                joinstyle=tk.ROUND,
            )

        if color_edge_families:
            segments_to_draw: list[
                tuple[float, tuple[float, float], tuple[float, float], str, float]
            ] = []
            for edge_key, occurrences in edge_occurrences.items():
                edge_kind = occurrences[0][0]
                if edge_kind == fold_sim.BOUNDARY:
                    best = max(occurrences, key=lambda item: item[1])
                    line_color = self._shade_color(
                        colors["preview_wire"], 0.92 + 0.10 * best[4]
                    )
                    segments_to_draw.append(
                        (best[1], best[2], best[3], line_color, 2.2)
                    )
                    continue

                if not self._cut_edge_is_split(occurrences):
                    if edge_kind == fold_sim.FOLD:
                        best = max(occurrences, key=lambda item: item[1])
                        line_color = self._shade_color(
                            colors["preview_crease"], 0.90 + 0.10 * best[4]
                        )
                        segments_to_draw.append(
                            (best[1], best[2], best[3], line_color, 1.3)
                        )
                    continue

                base_color = self._cut_edge_family_color(edge_key)
                for _, line_depth, start, end, edge_brightness in occurrences:
                    line_color = self._shade_color(
                        base_color, 0.92 + 0.08 * edge_brightness
                    )
                    if edge_kind == "mesh":
                        line_width = 1.2
                    else:
                        line_width = 1.7
                    segments_to_draw.append(
                        (line_depth, start, end, line_color, line_width)
                    )
        else:
            for edge_key, occurrences in edge_occurrences.items():
                best = max(occurrences, key=lambda item: item[1])
                edge_kind, line_depth, start, end, edge_brightness = best
                if edge_kind == "mesh":
                    continue
                if edge_kind == fold_sim.BOUNDARY:
                    line_color = self._shade_color(
                        colors["preview_wire"], 0.92 + 0.10 * edge_brightness
                    )
                    line_width = 2.2
                else:
                    line_color = self._shade_color(
                        colors["preview_crease"], 0.90 + 0.10 * edge_brightness
                    )
                    line_width = 1.3
                edge_segments[edge_key] = (
                    line_depth,
                    start,
                    end,
                    line_color,
                    line_width,
                )
            segments_to_draw = list(edge_segments.values())

        for _, start, end, line_color, width_value in sorted(
            segments_to_draw, key=lambda item: item[0]
        ):
            canvas.create_line(
                start[0],
                start[1],
                end[0],
                end[1],
                fill=line_color,
                width=width_value,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )

    def _draw_sheet_background(self, width: int, height: int) -> None:
        canvas = self.canvas
        colors = self.COLORS

        canvas.create_oval(
            -width * 0.08,
            -height * 0.02,
            width * 0.38,
            height * 0.40,
            fill=colors["wash_one"],
            outline="",
        )
        canvas.create_oval(
            width * 0.64,
            height * 0.54,
            width * 1.08,
            height * 1.02,
            fill=colors["wash_two"],
            outline="",
        )
        for offset in range(-height, width + height, 90):
            canvas.create_line(
                offset,
                0,
                offset + height,
                height,
                fill=colors["pattern_line"],
                width=1,
            )

    def _draw_preview_background(self, width: int, height: int) -> None:
        canvas = self.preview_canvas
        colors = self.COLORS

        canvas.create_oval(
            width * 0.08,
            height * 0.04,
            width * 0.92,
            height * 0.82,
            fill=colors["preview_glow"],
            outline="",
        )
        canvas.create_oval(
            width * 0.62,
            -height * 0.10,
            width * 1.10,
            height * 0.42,
            fill=colors["preview_wash"],
            outline="",
        )
        for offset in range(-height, width + height, 130):
            canvas.create_line(
                offset,
                0,
                offset + height,
                height,
                fill=self._shade_color(colors["preview_wash"], 1.12),
                width=1,
            )

    def _draw_vertex_label(
        self,
        index: int,
        vertex: cp.Vertex,
        x: float,
        y: float,
        side: float,
    ) -> None:
        norm_x = vertex.x / side
        norm_y = vertex.y / side

        shift_x = 14 if norm_x < 0.55 else -14
        shift_y = 14 if norm_y < 0.55 else -14
        anchor = "nw"
        if norm_x >= 0.55 and norm_y < 0.55:
            anchor = "ne"
        elif norm_x < 0.55 and norm_y >= 0.55:
            anchor = "sw"
        elif norm_x >= 0.55 and norm_y >= 0.55:
            anchor = "se"

        text_id = self.canvas.create_text(
            x + shift_x,
            y + shift_y,
            text=str(index),
            anchor=anchor,
            fill=self.COLORS["ink"],
            font=self.fonts["small"],
        )
        x1, y1, x2, y2 = self.canvas.bbox(text_id)
        pad_x = 6
        pad_y = 4
        rect_id = self.canvas.create_rectangle(
            x1 - pad_x,
            y1 - pad_y,
            x2 + pad_x,
            y2 + pad_y,
            fill=self.COLORS["label_bg"],
            outline=self.COLORS["label_outline"],
        )
        self.canvas.tag_lower(rect_id, text_id)

    def _preview_view_rotation(self) -> np.ndarray:
        rotate_x = self._rotation_x(self._preview_orbit_pitch)
        rotate_y = self._rotation_y(self._preview_orbit_yaw)
        rotate_z = self._rotation_z(self._preview_orbit_roll)
        return rotate_z @ rotate_y @ rotate_x

    def _rotation_x(self, angle: float) -> np.ndarray:
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, cosine, -sine],
                [0.0, sine, cosine],
            ],
            dtype=float,
        )

    def _rotation_y(self, angle: float) -> np.ndarray:
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return np.array(
            [
                [cosine, 0.0, sine],
                [0.0, 1.0, 0.0],
                [-sine, 0.0, cosine],
            ],
            dtype=float,
        )

    def _rotation_z(self, angle: float) -> np.ndarray:
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return np.array(
            [
                [cosine, -sine, 0.0],
                [sine, cosine, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

    def _polygon_normal(self, points: np.ndarray) -> np.ndarray:
        if len(points) < 3:
            return np.zeros(3, dtype=float)

        origin = points[0]
        for index in range(1, len(points) - 1):
            first = points[index] - origin
            second = points[index + 1] - origin
            normal = np.cross(first, second)
            if np.linalg.norm(normal) > 1e-8:
                return normal
        return np.zeros(3, dtype=float)

    def _shade_color(self, color: str, factor: float) -> str:
        factor = min(max(factor, 0.0), 1.8)
        red = min(max(int(int(color[1:3], 16) * factor), 0), 255)
        green = min(max(int(int(color[3:5], 16) * factor), 0), 255)
        blue = min(max(int(int(color[5:7], 16) * factor), 0), 255)
        return f"#{red:02x}{green:02x}{blue:02x}"

    def _cut_edge_family_color(self, edge_key: tuple[int, int]) -> str:
        palette = self.EDGE_FAMILY_COLORS
        seed = edge_key[0] * 131 + edge_key[1] * 17
        base = palette[seed % len(palette)]
        shift = ((seed // len(palette)) % 5) - 2
        factor = 1.0 + 0.08 * shift
        return self._shade_color(base, factor)

    def _cut_edge_is_split(
        self,
        occurrences: list[
            tuple[str, float, tuple[float, float], tuple[float, float], float]
        ],
    ) -> bool:
        if len(occurrences) < 2:
            return False

        split_threshold = 3.0
        for index, first in enumerate(occurrences):
            for second in occurrences[index + 1 :]:
                if (
                    self._segment_screen_distance(
                        first[2], first[3], second[2], second[3]
                    )
                    > split_threshold
                ):
                    return True
        return False

    def _segment_screen_distance(
        self,
        first_start: tuple[float, float],
        first_end: tuple[float, float],
        second_start: tuple[float, float],
        second_end: tuple[float, float],
    ) -> float:
        direct = (
            math.dist(first_start, second_start) + math.dist(first_end, second_end)
        ) * 0.5
        flipped = (
            math.dist(first_start, second_end) + math.dist(first_end, second_start)
        ) * 0.5
        return min(direct, flipped)

    def _fold_color(self, fold_type: int) -> str:
        if fold_type == 0:
            return self.COLORS["mountain"]
        if fold_type == 1:
            return self.COLORS["valley"]
        return self.COLORS["neutral_fold"]


def main() -> None:
    root = tk.Tk()
    CPGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
