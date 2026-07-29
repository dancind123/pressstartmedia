from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pressstart_media.version import BUILD_LABEL


class StatusRenderer:
    LOGO_PATH = Path(
        "/home/media/PressStart/assets/wallpaper.png"
    )

    STATUS_IMAGE_PATH = Path(
        "/home/media/PressStart/runtime/status.png"
    )

    FONT_PATH = Path(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )

    FONT_BOLD_PATH = Path(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    )

    TITLE_SIZE_RATIO = 0.045
    MESSAGE_SIZE_RATIO = 0.026
    BUILD_SIZE_RATIO = 0.016

    PANEL_WIDTH_RATIO = 0.78
    PANEL_HEIGHT_RATIO = 0.34
    PANEL_OPACITY = 190
    PANEL_MARGIN_RATIO = 0.045
    TEXT_SPACING_RATIO = 0.018

    @staticmethod
    def _load_font(
        path: Path,
        size: int,
    ) -> ImageFont.FreeTypeFont:
        if not path.is_file():
            raise RuntimeError(
                f"Status font was not found: {path}"
            )

        return ImageFont.truetype(
            str(path),
            size=max(size, 12),
        )

    @staticmethod
    def _centered_text_x(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        image_width: int,
    ) -> int:
        bounds = draw.textbbox(
            (0, 0),
            text,
            font=font,
        )

        text_width = bounds[2] - bounds[0]

        return max(
            0,
            int((image_width - text_width) / 2),
        )

    def render(
        self,
        title: str,
        message: str = "",
    ) -> Path:
        if not self.LOGO_PATH.is_file():
            raise RuntimeError(
                f"Logo image was not found: {self.LOGO_PATH}"
            )

        with Image.open(self.LOGO_PATH) as source:
            image = source.convert("RGBA")

        width, height = image.size

        overlay = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0),
        )

        overlay_draw = ImageDraw.Draw(overlay)

        panel_width = int(
            width * self.PANEL_WIDTH_RATIO
        )

        panel_height = int(
            height * self.PANEL_HEIGHT_RATIO
        )

        panel_left = int(
            (width - panel_width) / 2
        )

        panel_top = int(
            height
            - panel_height
            - (height * self.PANEL_MARGIN_RATIO)
        )

        panel_right = panel_left + panel_width
        panel_bottom = panel_top + panel_height

        corner_radius = max(
            12,
            int(height * 0.02),
        )

        overlay_draw.rounded_rectangle(
            (
                panel_left,
                panel_top,
                panel_right,
                panel_bottom,
            ),
            radius=corner_radius,
            fill=(0, 0, 0, self.PANEL_OPACITY),
        )

        image = Image.alpha_composite(
            image,
            overlay,
        )

        draw = ImageDraw.Draw(image)

        title_font = self._load_font(
            self.FONT_BOLD_PATH,
            int(height * self.TITLE_SIZE_RATIO),
        )

        message_font = self._load_font(
            self.FONT_PATH,
            int(height * self.MESSAGE_SIZE_RATIO),
        )

        build_font = self._load_font(
            self.FONT_PATH,
            int(height * self.BUILD_SIZE_RATIO),
        )

        spacing = max(
            8,
            int(height * self.TEXT_SPACING_RATIO),
        )

        title_bounds = draw.multiline_textbbox(
            (0, 0),
            title,
            font=title_font,
            spacing=spacing,
            align="center",
        )

        title_height = (
            title_bounds[3] - title_bounds[1]
        )

        message_bounds = draw.multiline_textbbox(
            (0, 0),
            message,
            font=message_font,
            spacing=spacing,
            align="center",
        )

        message_height = (
            message_bounds[3] - message_bounds[1]
            if message
            else 0
        )

        build_bounds = draw.textbbox(
            (0, 0),
            BUILD_LABEL,
            font=build_font,
        )

        build_height = (
            build_bounds[3] - build_bounds[1]
        )

        content_height = (
            title_height
            + build_height
            + (spacing * 2)
        )

        if message:
            content_height += (
                message_height + spacing
            )

        y = panel_top + int(
            (panel_height - content_height) / 2
        )

        title_x = self._centered_text_x(
            draw,
            max(
                title.splitlines(),
                key=len,
                default=title,
            ),
            title_font,
            width,
        )

        draw.multiline_text(
            (title_x, y),
            title,
            font=title_font,
            fill=(255, 255, 255, 255),
            spacing=spacing,
            align="center",
        )

        y += title_height + spacing

        if message:
            message_x = self._centered_text_x(
                draw,
                max(
                    message.splitlines(),
                    key=len,
                    default="",
                ),
                message_font,
                width,
            )

            draw.multiline_text(
                (message_x, y),
                message,
                font=message_font,
                fill=(235, 235, 235, 255),
                spacing=spacing,
                align="center",
            )

            y += message_height + spacing

        build_x = self._centered_text_x(
            draw,
            BUILD_LABEL,
            build_font,
            width,
        )

        draw.text(
            (build_x, y),
            BUILD_LABEL,
            font=build_font,
            fill=(190, 190, 190, 255),
        )

        self.STATUS_IMAGE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = (
            self.STATUS_IMAGE_PATH.with_suffix(".tmp.png")
        )

        image.convert("RGB").save(
            temporary_path,
            format="PNG",
        )

        temporary_path.replace(
            self.STATUS_IMAGE_PATH
        )

        return self.STATUS_IMAGE_PATH
