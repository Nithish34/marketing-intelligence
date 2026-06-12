import os
import json

brands_data = [
    ("ai_productivity_brand.md", "NotePilot AI", "knowledge workers", "AI-powered note-taking and knowledge management"),
    ("automotive_service_brand.md", "AutoCare Local", "car owners", "trusted local automotive repair and maintenance"),
    ("b2b_logistics_brand.md", "LogiTrack Pro", "operations teams", "enterprise supply chain visibility and tracking"),
    ("b2b_saas_crm_brand.md", "SalesFlow CRM", "small B2B sales teams", "streamlined customer relationship management"),
    ("coffee_subscription_brand.md", "BeanBox Express", "coffee lovers", "curated monthly specialty coffee deliveries"),
    ("cybersecurity_saas_brand.md", "SecureCloud", "IT teams", "cloud infrastructure security and monitoring"),
    ("ecommerce_skincare_brand.md", "GlowKind", "people with sensitive skin", "gentle, dermatologist-tested skincare routines"),
    ("edu_tech_brand.md", "StudyFlow AI", "college students", "AI-assisted study planning and assignment tracking"),
    ("enterprise_analytics_brand.md", "MetricsBoard", "enterprise teams", "centralized business intelligence dashboards"),
    ("event_planning_brand.md", "EventPlanner Pro", "companies", "corporate event and conference management"),
    ("fintech_budgeting_brand.md", "PocketPilot", "young professionals", "automated personal finance and budgeting"),
    ("fitness_studio_brand.md", "FitStart Studio", "beginners and busy professionals", "welcoming, high-intensity group fitness classes"),
    ("gaming_app_brand.md", "PuzzleQuest Mobile", "casual mobile gamers", "relaxing and engaging puzzle adventures"),
    ("healthcare_clinic_brand.md", "Neighborhood Care Clinic", "local families", "accessible and compassionate family healthcare"),
    ("home_services_brand.md", "HomeFix Local", "homeowners", "reliable on-demand home repair and handyman services"),
    ("hr_recruiting_saas_brand.md", "HiringHub", "hiring teams", "applicant tracking and interview scheduling"),
    ("legal_services_brand.md", "BizLegal Advisor", "small business owners", "affordable corporate legal guidance and contracts"),
    ("marketplace_freelance_brand.md", "FreelanceHub", "small businesses", "connecting businesses with vetted freelance talent"),
    ("mental_wellness_app_brand.md", "MindCalm App", "people", "daily meditation and mental wellness tracking"),
    ("nonprofit_donation_brand.md", "Community Table Fund", "donors", "fighting local food insecurity and hunger"),
    ("online_course_creator_brand.md", "CourseBuilder", "independent creators", "platform for creating and selling online courses"),
    ("pet_care_ecommerce_brand.md", "Paws & Claws Boutique", "pet owners", "premium pet food and engaging toys"),
    ("real_estate_agent_brand.md", "Metro Home Guide", "first-time home buyers", "navigating the urban real estate market with ease"),
    ("restaurant_cafe_brand.md", "Corner Cup Cafe", "busy local customers", "artisanal coffee and quick, healthy breakfast options"),
    ("sample_brand.md", "Acme Campaign Builder", "small marketing teams", "all-in-one marketing automation and campaign builder"),
    ("sustainable_fashion_brand.md", "EcoWear Boutique", "style-conscious shoppers", "ethically sourced and sustainable clothing"),
    ("travel_hotel_brand.md", "StayLocal Boutique Hotel", "travelers", "authentic and luxurious local travel experiences"),
]

template = """# {product} Brand Context

{product} helps {audience} with {description}. 

Our core value proposition is delivering reliable, high-quality solutions tailored specifically for {audience} who need {description} without unnecessary complexity. We empower our users to achieve their goals faster, better, and with more confidence.

Brand voice: Professional yet approachable. We use clear, engaging language that builds trust. We are authoritative in our field but never condescending, always aiming to educate and uplift our audience.

Typical customers care about:
- Efficiency and saving time in their daily routines.
- High-quality results that they can rely on consistently.
- Responsive support and a brand that understands their specific pain points.
- Good value for money and transparent pricing.

Primary channels: LinkedIn, Twitter, targeted email newsletters, and our industry-leading blog.

Content style: Informative, structured, and visually clean. We prefer short paragraphs, bullet points for readability, and actionable takeaways in every piece of content. Case studies and customer testimonials are heavily featured.
"""

def main():
    kb_dir = "knowledge_base"
    if not os.path.exists(kb_dir):
        print(f"Directory {kb_dir} does not exist.")
        return

    for file_name, product, audience, desc in brands_data:
        file_path = os.path.join(kb_dir, file_name)
        
        # We add some variety for the StudyFlow AI example as per our implementation plan
        if file_name == "edu_tech_brand.md":
            content = f"""# StudyFlow AI Brand Context

StudyFlow AI helps college students manage their assignments, track deadlines, and optimize their study schedules using artificial intelligence. 

Our core value proposition is transforming overwhelming syllabi into actionable, personalized, and manageable daily tasks, reducing student anxiety and improving academic performance. 

Brand voice: Encouraging, organized, slightly witty, and highly empathetic to the stresses of academic life. We aim to sound like a smart, older peer mentor who has their life perfectly together.

Typical customers care about: 
- Never missing a deadline or forgetting an assignment.
- Maximizing free time without sacrificing grades.
- Reducing the feeling of being overwhelmed by multiple classes.
- Easy integration with their existing tools (Canvas, Blackboard, Google Calendar).

Primary channels: TikTok, Instagram Reels, YouTube sponsorships, and campus ambassador programs.

Content style: Highly visual, fast-paced, and relatable. We use memes and trending audio on social media, paired with practical, actionable study tips. Blog and email content should be highly structured, using bullet points, bold text, and clear takeaways.
"""
        elif file_name == "ecommerce_skincare_brand.md":
             content = f"""# GlowKind Brand Context

GlowKind helps people with sensitive skin build gentle, dermatologist-tested skincare routines.

Our core value proposition is providing irritation-free, highly effective skincare products made from clean, sustainably sourced ingredients. We believe that everyone deserves to feel confident in their skin without compromising on safety.

Brand voice: Calming, educational, reassuring, and inclusive. We speak to our customers like a knowledgeable aesthetician—gentle, supportive, and deeply informed about skin health.

Typical customers care about:
- Avoiding redness, breakouts, and allergic reactions.
- Understanding exactly what ingredients are in their products.
- Achieving a natural, healthy glow rather than artificial perfection.
- Cruelty-free and eco-friendly packaging.

Primary channels: Instagram, Pinterest, YouTube tutorials, and email newsletters.

Content style: Aesthetic, minimal, and visually soothing. We use soft pastel colors, authentic user-generated content (no heavy filters), and step-by-step educational carousels.
"""
        elif file_name == "b2b_saas_crm_brand.md":
             content = f"""# SalesFlow CRM Brand Context

SalesFlow CRM helps small B2B sales teams streamline their customer relationship management.

Our core value proposition is offering an intuitive, zero-clutter CRM that focuses purely on closing deals rather than data entry. We eliminate the steep learning curve associated with enterprise CRMs, allowing small teams to get up and running in minutes.

Brand voice: Direct, ambitious, data-driven, and slightly punchy. We speak the language of sales—velocity, pipelines, and conversions—while keeping things highly practical.

Typical customers care about:
- Reducing the time spent logging calls and emails.
- Getting clear visibility into the sales pipeline.
- Automating repetitive follow-up tasks.
- Seamless integration with Gmail and Outlook.

Primary channels: LinkedIn, B2B podcasts, targeted webinars, and high-value whitepapers.

Content style: Data-heavy, actionable, and straight to the point. We use bold typography, clear charts, and templates that sales reps can copy-paste. No fluff.
"""
        else:
            content = template.format(product=product, audience=audience, description=desc)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {file_name}")

if __name__ == "__main__":
    main()
