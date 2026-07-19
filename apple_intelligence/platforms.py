"""Platform presets, bundles, and styles."""

APPLE_STYLES = ["animation", "illustration", "sketch", "emoji", "messages-background"]

FILTERS = [
    "blur", "sharpen", "brightness", "contrast", "saturation",
    "vignette", "sepia", "noir", "instant", "chrome",
]

# width x height, in pixels
PLATFORM_PRESETS = {
    # Instagram
    "instagram_post":       (1080, 1080),
    "instagram_portrait":   (1080, 1350),
    "instagram_landscape":  (1080, 566),
    "instagram_story":      (1080, 1920),
    "instagram_reel_cover": (1080, 1920),
    "instagram_carousel":   (1080, 1350),
    # Facebook
    "facebook_post":        (1200, 630),
    "facebook_cover":       (820, 312),
    "facebook_event":       (1920, 1005),
    "facebook_story":       (1080, 1920),
    "facebook_reel_cover":  (1080, 1920),
    # X / Twitter
    "twitter_post":         (1600, 900),
    "twitter_header":       (1500, 500),
    "twitter_card":         (1200, 628),
    # LinkedIn
    "linkedin_post":        (1200, 627),
    "linkedin_cover":       (1584, 396),
    "linkedin_article":     (744, 400),
    "linkedin_newsletter":  (1200, 627),
    # Pinterest
    "pinterest_pin":        (1000, 1500),
    "pinterest_standard":   (1000, 1000),
    "pinterest_long":       (1000, 2100),
    # YouTube
    "youtube_thumbnail":    (1280, 720),
    "youtube_banner":       (2560, 1440),
    "youtube_community":    (1200, 628),
    # TikTok
    "tiktok":               (1080, 1920),
    "tiktok_cover":         (1080, 1440),
    # Threads
    "threads_post":         (1080, 1080),
    "threads_portrait":     (1080, 1350),
    # Blog / Web
    "blog_header":          (1600, 800),
    "blog_inline":          (1200, 800),
    "blog_thumbnail":       (600, 400),
    "og_image":             (1200, 630),
    "email_header":         (600, 200),
    "email_hero":           (600, 400),
    # Thumbnails & Misc
    "square_thumbnail":     (600, 600),
    "discord_banner":       (960, 540),
    "twitch_banner":        (1200, 480),
    "spotify_playlist":     (300, 300),
    "app_icon_1024":        (1024, 1024),
    "app_icon_512":         (512, 512),
    "app_icon_180":         (180, 180),
    "logo_transparent":     (512, 512),
}

PLATFORM_BUNDLES = {
    "full_social": [
        "instagram_post", "instagram_portrait", "instagram_story",
        "facebook_post", "twitter_post", "linkedin_post",
        "pinterest_pin", "youtube_thumbnail", "tiktok",
    ],
    "instagram_set": [
        "instagram_post", "instagram_portrait", "instagram_story",
        "instagram_reel_cover", "instagram_carousel",
    ],
    "blog_set": [
        "blog_header", "blog_inline", "blog_thumbnail",
        "og_image", "square_thumbnail",
    ],
    "startup_kit": [
        "og_image", "twitter_post", "linkedin_post",
        "blog_header", "email_header",
    ],
    "short_form_video": [
        "tiktok", "instagram_reel_cover", "facebook_reel_cover",
        "instagram_story",
    ],
    "youtube_set": [
        "youtube_thumbnail", "youtube_banner", "youtube_community",
    ],
}
