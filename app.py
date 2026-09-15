from flask import Flask, request, jsonify, session, render_template, redirect, url_for
import re
from urllib.parse import unquote, urlparse
import pg8000.native
from flask_bcrypt import Bcrypt
import google.generativeai as genai
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import uuid
import random

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'mindspace_secret_key_2024')
bcrypt = Bcrypt(app)

# Database connection
class _NativeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.position = 0

    def execute(self, query, parameters=()):
        parameter_names = [f"param_{index}" for index in range(len(parameters))]
        parameter_values = dict(zip(parameter_names, parameters))
        parameter_index = 0

        def replace_parameter(_match):
            nonlocal parameter_index
            name = parameter_names[parameter_index]
            parameter_index += 1
            return f":{name}"

        native_query = re.sub(r"%s", replace_parameter, query)
        self.rows = self.connection.run(native_query, **parameter_values)
        self.position = 0
        column_names = [column["name"] for column in (self.connection.columns or [])]
        self.rows = [dict(zip(column_names, row)) for row in self.rows]
        return self

    def fetchone(self):
        if self.position >= len(self.rows):
            return None
        row = self.rows[self.position]
        self.position += 1
        return row

    def fetchall(self):
        rows = self.rows[self.position:]
        self.position = len(self.rows)
        return rows

    def close(self):
        pass


class _NativeConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self, **_kwargs):
        return _NativeCursor(self.connection)

    def commit(self):
        self.connection.run("COMMIT")

    def rollback(self):
        self.connection.run("ROLLBACK")

    def close(self):
        self.connection.close()


def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    parsed_url = urlparse(database_url)
    if parsed_url.scheme not in ('postgresql', 'postgres'):
        raise ValueError("DATABASE_URL must use the postgresql:// scheme")

    database = parsed_url.path.lstrip('/')
    if not parsed_url.username or not database:
        raise ValueError("DATABASE_URL must include a username and database name")

    connection = pg8000.native.Connection(
        user=unquote(parsed_url.username),
        password=unquote(parsed_url.password or ''),
        host=parsed_url.hostname or 'localhost',
        port=parsed_url.port or 5432,
        database=unquote(database),
    )
    return _NativeConnection(connection)

# Local AI Response Function - IMPROVED VERSION
def local_ai_response(message):
    """Enhanced local AI with better pattern matching and contextual responses"""
    original_message = message
    message = message.lower().strip()

    # Keywords for different emotional states and topics
    greetings = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening", "hola", "namaste"]
    farewells = ["bye", "goodbye", "see you", "later", "cya", "gotta go", "take care"]
    feelings_sad = ["sad", "unhappy", "depressed", "down", "lonely", "angry", "upset", "cry", "hurt", "pain", "suffering", "miserable", "awful", "terrible", "hopeless"]
    feelings_happy = ["happy", "good", "great", "awesome", "excited", "joyful", "fine", "amazing", "wonderful", "fantastic", "excellent", "brilliant"]
    feelings_anxious = ["anxious", "nervous", "worried", "scared", "afraid", "panic", "stress", "tense", "overwhelmed"]
    feelings_confused = ["confused", "unsure", "doubt", "lost", "uncertain", "don't know", "not sure"]
    feelings_tired = ["tired", "exhausted", "sleepy", "fatigue", "worn out", "drained", "burnout"]
    
    hobbies = ["game", "gaming", "music", "movie", "film", "read", "reading", "book", "sports", "travel", "exercise", "workout", "gym", "drawing", "painting", "art", "coding", "programming"]
    help_keywords = ["help", "advice", "support", "tips", "suggest", "guide", "assist", "need you"]
    motivation_keywords = ["motivate", "motivation", "inspire", "can't do", "give up", "hopeless", "impossible", "difficult", "hard", "struggle"]
    compliments = ["thank", "thanks", "appreciate", "grateful", "you're great", "you're awesome", "love you"]
    jokes_keywords = ["joke", "funny", "laugh", "humor", "make me laugh", "cheer me up"]
    study_keywords = ["study", "studying", "exam", "test", "school", "college", "university", "homework", "assignment", "subject", "marks", "grades", "learning"]
    weather_keywords = ["weather", "rain", "raining", "sunny", "cold", "hot", "temperature", "climate"]
    love_keywords = ["love", "crush", "romantic", "relationship", "boyfriend", "girlfriend", "dating", "miss someone"]
    gratitude_keywords = ["grateful", "thankful", "blessed", "fortunate", "lucky"]
    health_keywords = ["sick", "ill", "pain", "headache", "fever", "health", "doctor", "medicine"]
    work_keywords = ["work", "job", "office", "boss", "colleague", "project", "deadline", "meeting", "career"]
    sleep_keywords = ["sleep", "insomnia", "can't sleep", "nightmare", "dream", "rest"]
    food_keywords = ["hungry", "food", "eat", "eating", "meal", "breakfast", "lunch", "dinner", "recipe"]
    
    responses = {
        "greetings": [
            "Hey there! 😊 I'm really glad you reached out. How's your day treating you?",
            "Hi! It's wonderful to hear from you. What's on your mind today?",
            "Hello! I hope you're doing well. Want to chat about something?",
            "Hey! Great to see you here. How are you feeling right now?",
            "Hi there! Your message brightened my day. What would you like to talk about?",
            "Hello friend! 🌟 How's everything going with you?",
            "Hey! I'm here and ready to listen. What's up?",
            "Hi! So happy you're here. Tell me, what's happening in your world?",
        ],
        "farewells": [
            "Goodbye for now! 💙 Remember, I'm here whenever you need to talk. Take care!",
            "See you soon! I hope the rest of your day is wonderful. Stay positive! 🌟",
            "Bye! It was great chatting with you. Come back anytime you need support! 😊",
            "Take care! Remember to be kind to yourself. I'll be here when you return! 💫",
            "Farewell! Keep your head up and remember - you're doing great! ✨",
            "See you later! Don't forget to take breaks and breathe. You've got this! 🌈",
            "Goodbye! Stay strong and keep moving forward. I'm always here for you! 💪",
        ],
        "feelings_sad": [
            "I'm really sorry you're going through this. 💙 It's completely okay to feel sad - your feelings are valid. Want to talk about what's bothering you?",
            "That sounds really tough, and I hear you. 🤗 Sometimes just expressing our feelings helps. I'm here to listen without judgment.",
            "I understand how heavy sadness can feel. You're brave for opening up about it. Would you like to share more about what's making you feel this way?",
            "Your feelings matter, and it's okay not to be okay. 💛 Take your time - I'm here to support you through this difficult moment.",
            "I can sense you're hurting, and I want you to know you're not alone. Let's work through this together, one step at a time.",
            "Sadness is a natural emotion, even though it feels overwhelming. 🌧️ Remember, storms don't last forever. How long have you been feeling this way?",
            "I'm here for you during this difficult time. Sometimes talking helps lighten the emotional load. What would help you feel better right now?",
            "It takes courage to acknowledge when we're struggling. 💪 I'm proud of you for reaching out. Let's talk about what's weighing on your heart.",
        ],
        "feelings_happy": [
            "That's wonderful! 🎉 I love hearing positive news! What made your day so special?",
            "Yay! Your happiness is contagious! 😄 Tell me all about it - what's got you smiling?",
            "That's amazing! I'm so glad you're feeling good. What's the highlight of your day?",
            "Fantastic! 🌟 Keep that positive energy flowing! What brought this joy into your life?",
            "Love to hear it! 💫 Happiness looks great on you. Care to share the details?",
            "This is great news! 🎊 I'm thrilled for you! What happened?",
            "Wonderful! Your positive vibes are making my day better too! What's making you so happy?",
            "That's brilliant! 😊 Keep celebrating those good moments. What's the story?",
        ],
        "feelings_anxious": [
            "I hear that you're feeling anxious. 🫂 First, let's take a deep breath together - in for 4, hold for 4, out for 6. What's causing you stress?",
            "Anxiety can be really overwhelming. You're not alone in this. 💙 Can you tell me what specific thoughts are making you worried?",
            "When anxiety hits, it helps to ground yourself. Try focusing on 5 things you can see, 4 you can touch, 3 you can hear, 2 you can smell, and 1 you can taste. Want to talk about what's stressing you?",
            "I understand how scary anxiety feels. Remember, these feelings are temporary. 🌊 Let's work through this together - what triggered these feelings?",
            "Your anxiety is valid, but remember - thoughts aren't facts. 💭 What's the main worry on your mind right now?",
            "Feeling nervous is completely normal. Let's break down what's worrying you into smaller, manageable pieces. Where should we start?",
        ],
        "feelings_confused": [
            "It's okay to feel uncertain - confusion is just your mind processing options. 🤔 What's puzzling you?",
            "Being unsure is a normal part of decision-making. Let's think this through together. What's the situation?",
            "I get it - sometimes things feel overwhelming and unclear. Let's break it down step by step. What's confusing you?",
            "Confusion often means you're at a crossroads, which can actually be a good thing. 🛤️ Tell me what's on your mind.",
            "Don't worry about not having all the answers. Let's explore this together and find clarity. What are you uncertain about?",
            "Sometimes when we're confused, we just need to talk it out. I'm here to help you sort through your thoughts. What's the main issue?",
        ],
        "feelings_tired": [
            "Sounds like you need some rest. 😴 Have you been getting enough sleep? Remember, taking care of yourself isn't selfish - it's essential.",
            "Burnout is real, and it sounds like you might be experiencing it. 🛌 When was the last time you took a proper break?",
            "Being tired - physically or mentally - is your body's way of asking for care. What's been draining your energy?",
            "Exhaustion can make everything feel harder. 💤 Is there anything I can help with to make things easier for you?",
            "Sometimes fatigue is emotional, not just physical. What's been weighing on you lately? Let's lighten the load.",
        ],
        "hobbies": [
            "That's a great hobby! 🎮🎨 Hobbies are so important for mental wellness. How did you get into it?",
            "I love that you have something you're passionate about! 🌟 What's your favorite part about doing it?",
            "Hobbies are wonderful for relaxation and self-expression. How often do you get to enjoy this activity?",
            "That sounds really enjoyable! Having creative outlets is so healthy. What draws you to this hobby?",
            "It's awesome that you have something that brings you joy! 💫 Tell me more about what you love about it.",
        ],
        "help_keywords": [
            "Of course, I'm here to help! 🤝 Tell me more about what's going on, and we'll figure it out together.",
            "I want to support you through this. Let's break down the situation - what's the main challenge you're facing?",
            "You've taken a brave first step by asking for help. 💪 What specific area do you need guidance with?",
            "I'm listening and ready to assist. Let's tackle this together, one step at a time. What's troubling you?",
            "Help is on the way! 🆘 Tell me everything - what do you need support with?",
            "I'm here for you. Let's work through this systematically. What's the most pressing issue right now?",
        ],
        "motivation_keywords": [
            "Hey, I know it feels tough right now, but remember - progress isn't linear. 💪 Every small step counts. What's one tiny thing you can do today?",
            "You're stronger than you think! 🌟 Even when progress feels slow, you're moving forward. Keep going!",
            "Difficult doesn't mean impossible. You've overcome challenges before, and you'll overcome this one too. 🔥 What's making you feel this way?",
            "Remember why you started. Your journey matters, and so do you. 💫 Don't give up - you're closer than you think!",
            "Every champion was once a beginner who refused to give up. 🏆 You've got this! What's the next small step you can take?",
            "Believe in yourself even when it's hard. 🌈 Your effort is never wasted. What would make today feel like a small win?",
        ],
        "compliments": [
            "That's so kind of you to say! 😊 Thank you! Your words really brighten my day.",
            "I really appreciate that! 💙 It means a lot. How can I help you today?",
            "Thank you so much! Your kindness is wonderful. 🌟 What else would you like to talk about?",
            "Aww, you're very sweet! 😊 I'm grateful for your appreciation. What's on your mind?",
            "That's very thoughtful! Thank you! 💫 I'm happy to be here for you.",
        ],
        "jokes_keywords": [
            "Why did the therapist bring a ladder to work? Because they help people reach new heights! 😄 Want another one?",
            "What do you call a happy brain? A no-brainer! 🧠😂 Need more laughs?",
            "Why don't mental health professionals ever get lost? They always know how to process their feelings! 😄",
            "What did one neuron say to the other? 'I've got a good connection with you!' ⚡😂",
            "Why did the meditation teacher refuse anesthesia? They wanted to be present for the operation! 🧘‍♀️😄",
        ],
        "study_keywords": [
            "Studying can be challenging! 📚 Remember to take breaks - your brain needs rest to retain information better. What subject are you working on?",
            "Academic stress is real! The key is consistent, manageable study sessions rather than cramming. 💡 How can I help with your studies?",
            "Remember: breaks actually improve learning! Try the Pomodoro technique - 25 minutes study, 5 minutes break. 🎯 What are you studying?",
            "Exams can be stressful, but you're capable! 💪 Focus on understanding concepts, not just memorizing. Need any study tips?",
            "Don't forget - grades don't define your worth! 📝 Do your best, take care of yourself, and remember learning is a journey. What's challenging you?",
        ],
        "weather_keywords": [
            "Weather can really affect our mood! ☀️🌧️ Whether it's sunny or rainy, each day has its beauty. How's the weather where you are?",
            "Isn't it interesting how weather impacts how we feel? 🌤️ What's your favorite type of weather?",
            "The weather can set the tone for our day! ⛅ Is it sunny, rainy, or something else where you are?",
        ],
        "love_keywords": [
            "Aww, matters of the heart! 💕 Love and relationships can be beautiful and complex. Want to talk about it?",
            "Romance and connection are important parts of life. 💖 How are things going in that area for you?",
            "Love is a powerful emotion! 💗 Whether it's joy or heartache, I'm here to listen. What's on your heart?",
            "Relationships can be wonderful and challenging. 💑 I'm here to talk through whatever you're feeling.",
        ],
        "gratitude_keywords": [
            "I love that you're practicing gratitude! 🙏 It's such a powerful way to improve mental wellness. What are you thankful for?",
            "Gratitude is a beautiful mindset! 💫 Research shows it significantly improves happiness. What's making you feel grateful today?",
            "Being thankful is wonderful for mental health! 🌟 I'm glad you're in a grateful space. What are you appreciating?",
        ],
        "health_keywords": [
            "I'm sorry you're not feeling well. 🤒 Physical health affects mental health too. Have you seen a doctor about this?",
            "Your health matters! 💊 Make sure to take care of yourself and get proper medical attention if needed. What's going on?",
            "Being sick is tough on both body and mind. 🏥 Rest is important! What symptoms are you experiencing?",
        ],
        "work_keywords": [
            "Work stress is very common! 💼 Remember to set boundaries and take breaks. What's happening at work?",
            "Job-related pressure can really affect wellbeing. 👔 Let's talk about what's stressing you at work.",
            "Career challenges are tough! 🏢 Remember, you're more than your job. What's going on with work?",
        ],
        "sleep_keywords": [
            "Sleep is crucial for mental health! 😴 Trouble sleeping? Try limiting screen time before bed and keeping a consistent schedule. What's affecting your sleep?",
            "Insomnia is frustrating! 🌙 Good sleep hygiene helps - dark room, cool temperature, no caffeine late in the day. How long have you had trouble sleeping?",
            "Sleep and mental health are closely connected. 💤 What's keeping you awake at night?",
        ],
        "food_keywords": [
            "What we eat affects how we feel! 🍎 Are you eating regularly and nutritiously? What's your relationship with food like?",
            "Nutrition and mental health are connected! 🥗 Make sure you're fueling your body properly. What's going on with eating?",
        ]
    }

    # Priority matching - check more specific patterns first
    
    # Check for question words to give contextual responses
    if message.startswith(("what", "why", "how", "when", "where", "who")):
        if "your name" in message or "who are you" in message:
            return "I'm your Personal AI Assistant, designed specifically for mental wellness support! 😊 I'm here to listen, support, and help you through whatever you're experiencing. What would you like to talk about?"
        elif "how are you" in message or "how're you" in message:
            return "I'm doing great, thank you for asking! 😊 More importantly - how are YOU doing today? I'm here to focus on you."
        elif "what can you do" in message or "what do you do" in message:
            return "I'm here to support your mental wellness! 💙 I can:\n• Listen to your feelings and concerns\n• Offer coping strategies and motivation\n• Provide a judgment-free space to express yourself\n• Help you work through challenges\n• Just be here when you need to talk\n\nWhat do you need right now?"
        elif "who created you" in message or "who made you" in message:
            return "I was created by a team that cares deeply about mental health and wanted to make support more accessible! 🌟 But enough about me - how can I help you today?"
    
    # Emotional states (prioritized)
    if any(word in message for word in feelings_sad):
        return random.choice(responses["feelings_sad"])
    elif any(word in message for word in feelings_anxious):
        return random.choice(responses["feelings_anxious"])
    elif any(word in message for word in feelings_tired):
        return random.choice(responses["feelings_tired"])
    elif any(word in message for word in feelings_happy):
        return random.choice(responses["feelings_happy"])
    elif any(word in message for word in feelings_confused):
        return random.choice(responses["feelings_confused"])
    
    # Specific topics
    if any(word in message for word in greetings):
        return random.choice(responses["greetings"])
    elif any(word in message for word in farewells):
        return random.choice(responses["farewells"])
    elif any(word in message for word in motivation_keywords):
        return random.choice(responses["motivation_keywords"])
    elif any(word in message for word in help_keywords):
        return random.choice(responses["help_keywords"])
    elif any(word in message for word in compliments):
        return random.choice(responses["compliments"])
    elif any(word in message for word in jokes_keywords):
        return random.choice(responses["jokes_keywords"])
    elif any(word in message for word in study_keywords):
        return random.choice(responses["study_keywords"])
    elif any(word in message for word in hobbies):
        return random.choice(responses["hobbies"])
    elif any(word in message for word in weather_keywords):
        return random.choice(responses["weather_keywords"])
    elif any(word in message for word in love_keywords):
        return random.choice(responses["love_keywords"])
    elif any(word in message for word in gratitude_keywords):
        return random.choice(responses["gratitude_keywords"])
    elif any(word in message for word in health_keywords):
        return random.choice(responses["health_keywords"])
    elif any(word in message for word in work_keywords):
        return random.choice(responses["work_keywords"])
    elif any(word in message for word in sleep_keywords):
        return random.choice(responses["sleep_keywords"])
    elif any(word in message for word in food_keywords):
        return random.choice(responses["food_keywords"])
    
    # Personal interactions
    if "love you" in message or "i love you" in message:
        return "That's so sweet! 💖 While I'm an AI, I'm here to support you with care and empathy. What would you like to talk about?"
    elif "bored" in message:
        return "Boredom can be a sign your mind is craving something new! 🎯 Want to hear a joke, talk about a hobby, or discuss something interesting?"
    elif "tell me about yourself" in message:
        return "I'm a mental wellness AI companion! 🤖💙 My purpose is to provide emotional support, listen without judgment, and help you navigate your feelings. I'm here 24/7 whenever you need someone to talk to. What about you - what brings you here today?"
    elif "lonely" in message or "alone" in message:
        return "I'm sorry you're feeling lonely. 🫂 You're not alone - I'm here with you right now. Loneliness is hard, but reaching out like this is a brave step. Want to talk about what's making you feel this way?"
    
    # Check for conversational patterns
    if "?" in original_message:
        return "That's a thoughtful question! 🤔 I'm here to explore it with you. Could you tell me more about what prompted this question? I want to understand your perspective better."
    
    # Default responses - more contextual and engaging
    generic = [
        "I'm listening closely. 👂 Tell me more about that - what's making you think about this?",
        "That's interesting! I'd love to understand more. Can you expand on what you mean?",
        "I hear you. 💙 What's the story behind this? I'm here to listen.",
        "Thanks for sharing that with me. How are you feeling about this situation?",
        "I'm curious to learn more about your thoughts on this. What else is on your mind?",
        "That's worth exploring. What emotions come up when you think about this?",
        "I appreciate you opening up. What would help you most right now - advice, just listening, or working through it together?",
        "Every thought and feeling you have is valid. 🌟 Would you like to dive deeper into this, or is there something else you'd like to talk about?",
    ]
    return random.choice(generic)


# Psychology professionals data
PSYCHOLOGY_PROFESSIONALS = [
    {
        "id": 1,
        "name": "Dr. Sarah Johnson",
        "specialization": "Clinical Psychologist",
        "experience": "12 years",
        "rating": 4.9,
        "contact": "+1-555-0101",
        "email": "sarah.johnson@mindspace.com",
        "availability": "Mon-Fri: 9AM-5PM",
        "image": "👩‍⚕",
        "bio": "Specializes in anxiety, depression, and trauma therapy with evidence-based approaches.",
        "languages": ["English", "Spanish"],
        "fee": "$120/session"
    },
    {
        "id": 2,
        "name": "Dr. Michael Chen",
        "specialization": "Cognitive Behavioral Therapist",
        "experience": "8 years",
        "rating": 4.8,
        "contact": "+1-555-0102",
        "email": "michael.chen@mindspace.com",
        "availability": "Tue-Sat: 10AM-6PM",
        "image": "👨‍⚕",
        "bio": "Expert in CBT techniques for managing stress, phobias, and behavioral patterns.",
        "languages": ["English", "Mandarin"],
        "fee": "$100/session"
    },
    {
        "id": 3,
        "name": "Dr. Emily Rodriguez",
        "specialization": "Child & Adolescent Psychologist",
        "experience": "10 years",
        "rating": 5.0,
        "contact": "+1-555-0103",
        "email": "emily.rodriguez@mindspace.com",
        "availability": "Mon-Thu: 2PM-8PM",
        "image": "👩‍⚕",
        "bio": "Dedicated to helping young minds navigate emotional challenges and development.",
        "languages": ["English", "Spanish", "French"],
        "fee": "$110/session"
    },
    {
        "id": 4,
        "name": "Dr. James Williams",
        "specialization": "Marriage & Family Therapist",
        "experience": "15 years",
        "rating": 4.7,
        "contact": "+1-555-0104",
        "email": "james.williams@mindspace.com",
        "availability": "Wed-Sun: 11AM-7PM",
        "image": "👨‍⚕",
        "bio": "Helps couples and families build stronger relationships and communication.",
        "languages": ["English"],
        "fee": "$150/session"
    }
]

# Meditation exercises
MEDITATION_EXERCISES = [
    {
        "id": 1,
        "title": "Deep Breathing Relaxation",
        "duration": "10 minutes",
        "difficulty": "Beginner",
        "description": "Focus on your breath, inhaling deeply through your nose and exhaling slowly through your mouth.",
        "benefits": ["Reduces stress", "Improves focus", "Calms nervous system"],
        "instructions": [
            "Find a comfortable seated position",
            "Close your eyes gently",
            "Breathe in slowly through your nose for 4 counts",
            "Hold for 4 counts",
            "Exhale through your mouth for 6 counts",
            "Repeat for 10 minutes"
        ],
        "icon": "🧘‍♀"
    },
    {
        "id": 2,
        "title": "Body Scan Meditation",
        "duration": "15 minutes",
        "difficulty": "Intermediate",
        "description": "Progressive relaxation technique focusing on each part of your body.",
        "benefits": ["Releases tension", "Improves body awareness", "Promotes better sleep"],
        "instructions": [
            "Lie down in a comfortable position",
            "Start from your toes and work upward",
            "Focus on each body part for 30 seconds",
            "Notice any tension and breathe into it",
            "Release and relax each area completely"
        ],
        "icon": "🛌"
    },
    {
        "id": 3,
        "title": "Mindful Visualization",
        "duration": "12 minutes",
        "difficulty": "Intermediate",
        "description": "Create peaceful mental imagery to reduce anxiety and stress.",
        "benefits": ["Reduces anxiety", "Enhances creativity", "Improves mood"],
        "instructions": [
            "Sit comfortably with eyes closed",
            "Imagine a peaceful place",
            "Engage all your senses in the visualization",
            "Stay present in this peaceful scene",
            "Gently return when ready"
        ],
        "icon": "🌅"
    }
]

# Music therapy tracks
MUSIC_TRACKS = [
    {
        "id": 1,
        "title": "Peaceful Flute Meditation",
        "duration": "60 minutes",
        "youtube_id": "z2gTzXgZoSo",
        "description": "Soothing flute music to calm your mind and reduce stress",
        "category": "Relaxation",
        "benefits": ["Deep relaxation", "Stress relief", "Better sleep"]
    },
    {
        "id": 2,
        "title": "Nature Sounds - Rain & Thunder",
        "duration": "45 minutes",
        "youtube_id": "nDq6TstdEi8",
        "description": "Gentle rain and distant thunder for peaceful meditation",
        "category": "Nature",
        "benefits": ["Meditation support", "Focus enhancement", "Anxiety reduction"]
    },
    {
        "id": 3,
        "title": "Binaural Beats - Focus",
        "duration": "30 minutes",
        "youtube_id": "WPni755-Krg",
        "description": "Alpha waves for enhanced concentration and productivity",
        "category": "Focus",
        "benefits": ["Improved concentration", "Mental clarity", "Productivity boost"]
    },
    {
        "id": 4,
        "title": "Piano for Sleep",
        "duration": "50 minutes",
        "youtube_id": "jIxas0a-KgM",
        "description": "Gentle piano melodies for restful sleep",
        "category": "Sleep",
        "benefits": ["Better sleep quality", "Relaxation", "Stress relief"]
    }
]

# Brain games
BRAIN_GAMES = [
    {
        "id": "1",
        "title": "Memory Matrix",
        "description": "Test your memory by remembering patterns and sequences. Improve your short-term memory and focus.",
        "difficulty": "Easy",
        "duration": "5-10 min",
        "benefits": ["Memory", "Focus", "Concentration"],
        "icon": "🧠",
        "url": None
    },
    {
        "id": "2",
        "title": "Number Challenge",
        "description": "Improve your numerical skills with fun math puzzles and calculations. Boost your problem-solving abilities.",
        "difficulty": "Medium",
        "duration": "10-15 min",
        "benefits": ["Math", "Logic", "Problem Solving"],
        "icon": "🔢",
        "url": "https://sudoku.com"
    },
    {
        "id": "3",
        "title": "Focus Trainer",
        "description": "Enhance your concentration and attention span with engaging focus exercises. Perfect for mindfulness training.",
        "difficulty": "Easy",
        "duration": "5-10 min",
        "benefits": ["Attention", "Timing", "Precision"],
        "icon": "🎯",
        "url": "https://play2048.co"
    },
    {
        "id": "4",
        "title": "Pattern Recognition",
        "description": "Identify patterns and sequences to train your visual processing and analytical thinking skills.",
        "difficulty": "Hard",
        "duration": "10-20 min",
        "benefits": ["Visual", "Analysis", "Critical Thinking"],
        "icon": "🎨",
        "url": "https://www.lumosity.com"
    },
    {
        "id": "5",
        "title": "Word Wizard",
        "description": "Expand your vocabulary and language skills with engaging word puzzles and crosswords.",
        "difficulty": "Medium",
        "duration": "8-12 min",
        "benefits": ["Vocabulary", "Language", "Creativity"],
        "icon": "📝",
        "url": "https://www.wordgames.com"
    },
    {
        "id": "6",
        "title": "Reaction Speed",
        "description": "Test and improve your reaction time with fast-paced clicking challenges. Perfect for mental agility.",
        "difficulty": "Easy",
        "duration": "3-5 min",
        "benefits": ["Speed", "Reflexes", "Alertness"],
        "icon": "⚡",
        "url": "https://humanbenchmark.com/tests/reactiontime"
    }
]

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Create tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nexas_users (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                age INTEGER,
                mobile TEXT,
                password TEXT NOT NULL,
                profile_type TEXT DEFAULT 'user',
                auth_user_id UUID DEFAULT gen_random_uuid(),
                registered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id UUID REFERENCES nexas_users(auth_user_id),
                message_date DATE DEFAULT CURRENT_DATE,
                message_count INTEGER DEFAULT 0,
                UNIQUE(user_id, message_date)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS community_posts (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id UUID REFERENCES nexas_users(auth_user_id),
                author_name TEXT,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                likes_count INTEGER DEFAULT 0
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id UUID REFERENCES nexas_users(auth_user_id),
                activity_type TEXT NOT NULL,
                activity_title TEXT,
                activity_description TEXT,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def log_activity(user_id, activity_type, title, description):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO user_activity (user_id, activity_type, activity_title, activity_description)
            VALUES (%s, %s, %s, %s)
        """, (user_id, activity_type, title, description))
        conn.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def get_user_message_count(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    today = datetime.now().date()
    
    try:
        cur.execute(
            "SELECT message_count FROM user_messages WHERE user_id = %s AND message_date = %s",
            (user_id, today)
        )
        result = cur.fetchone()
        return result['message_count'] if result else 0
    except Exception as e:
        print(f"Error getting message count: {e}")
        return 0
    finally:
        cur.close()
        conn.close()

def increment_message_count(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    today = datetime.now().date()
    
    try:
        cur.execute("""
            INSERT INTO user_messages (user_id, message_date, message_count) 
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, message_date) 
            DO UPDATE SET message_count = user_messages.message_count + 1
        """, (user_id, today))
        conn.commit()
    except Exception as e:
        print(f"Error incrementing message count: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def get_gemini_response(message):
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(f"""
        You are a compassionate mental health assistant. Provide supportive, empathetic responses.
        User message: {message}
        
        Guidelines:
        - Be warm, understanding, and non-judgmental
        - Offer practical coping strategies when appropriate
        - Encourage professional help for serious concerns
        - Keep responses under 200 words
        - Use a conversational, friendly tone
        """)
        return response.text
    except Exception as e:
        return "I'm here to listen and support you. Could you tell me more about how you're feeling today?"

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    conn = get_db_connection()
    data = request.json
    full_name = data.get('full_name')
    email = data.get('email')
    password = data.get('password')

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO nexas_users (full_name, email, password) VALUES (%s, %s, %s) RETURNING *",
            (full_name, email, hashed_password)
        )
        new_user = cur.fetchone()
        conn.commit()
        
        session['user_id'] = str(new_user['auth_user_id'])
        session['full_name'] = full_name
        session['email'] = email
        session['registered_at'] = new_user['registered_at'].strftime('%Y-%m-%d')
        
        return jsonify({'success': True, 'message': 'Account created successfully'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Email already exists'})
    finally:
        cur.close()
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    conn = get_db_connection()
    data = request.json
    email = data.get('email')
    password = data.get('password')

    cur = conn.cursor()
    cur.execute("SELECT * FROM nexas_users WHERE email = %s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and bcrypt.check_password_hash(user['password'], password):
        session['user_id'] = str(user['auth_user_id'])
        session['full_name'] = user['full_name']
        session['email'] = user['email']
        session['registered_at'] = user['registered_at'].strftime('%Y-%m-%d')
        return jsonify({'success': True, 'message': 'Login successful'})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('dashboard.html', 
                         name=session['full_name'],
                         email=session['email'])
    
@app.route('/api/user_stats')
def get_user_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    message_count = get_user_message_count(session['user_id'])
    messages_left = max(0, 50 - message_count)
    
    registered = datetime.strptime(session.get('registered_at', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d')
    days_active = (datetime.now() - registered).days + 1
    
    return jsonify({
        'success': True,
        'messages_left': messages_left,
        'days_active': days_active,
        'current_streak': min(days_active, 7),
        'total_minutes': days_active * 15
    })

@app.route('/api/message_limit')
def get_message_limit():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    message_count = get_user_message_count(session['user_id'])
    limit_reached = message_count >= 50
    
    return jsonify({
        'message_count': message_count,
        'limit_reached': limit_reached
    })

@app.route('/api/recent_activity')
def get_recent_activity():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT activity_type as type, activity_title as title, 
                   activity_description as description, timestamp
            FROM user_activity 
            WHERE user_id = %s 
            ORDER BY timestamp DESC 
            LIMIT 5
        """, (session['user_id'],))
        activities = cur.fetchall()
        
        for activity in activities:
            activity['timestamp'] = activity['timestamp'].isoformat()
        
        return jsonify({
            'success': True,
            'activities': activities
        })
    except Exception as e:
        return jsonify({'success': False, 'activities': []})
    finally:
        cur.close()
        conn.close()

@app.route('/api/notifications')
def get_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    return jsonify({
        'success': True,
        'count': 0
    })

# SINGLE CHATBOT ROUTE - KEEP ONLY THIS ONE
@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        user_message = request.json.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'response': "I didn't receive any message. Could you please type something? I'm here to listen! 😊",
                'limit_reached': False
            })
        
        message_count = get_user_message_count(session['user_id'])
        if message_count >= 50:
            return jsonify({
                'response': "You've reached your daily limit of 50 messages. Upgrade for unlimited access! 💬",
                'limit_reached': True
            })
        
        increment_message_count(session['user_id'])
        
        # Use only local AI response
        try:
            response = local_ai_response(user_message)
            print(f"✅ Local AI response generated for: '{user_message[:50]}...'")
        except Exception as e:
            print(f"❌ Local AI error: {e}")
            response = "I apologize, but I'm having a moment of confusion. Could you rephrase that for me? I want to make sure I understand you correctly. 😊"
        
        log_activity(session['user_id'], 'chat', 'AI Assistant Chat', f'Chat: {user_message[:50]}...')
        
        return jsonify({
            'response': response,
            'limit_reached': False,
            'messages_used': message_count + 1
        })
    
    return render_template('chatbot.html', name=session['full_name'], email=session['email'])

@app.route('/professionals')
def professionals():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    log_activity(session['user_id'], 'professional', 'Viewed Professionals', 'Browsed mental health professionals')
    
    return render_template('professionals.html', 
                         name=session['full_name'],
                         email=session['email'],
                         professionals=PSYCHOLOGY_PROFESSIONALS)

@app.route('/meditation')
def meditation():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    log_activity(session['user_id'], 'meditation', 'Meditation Session', 'Accessed meditation exercises')
    
    return render_template('meditation.html', 
                         name=session['full_name'],
                         email=session['email'],
                         exercises=MEDITATION_EXERCISES)

@app.route('/music')
def music():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    log_activity(session['user_id'], 'music', 'Music Therapy', 'Listened to therapeutic music')
    
    return render_template('music.html', 
                         name=session['full_name'],
                         email=session['email'],
                         music_tracks=MUSIC_TRACKS)

@app.route('/games')
def games():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    log_activity(session['user_id'], 'game', 'Brain Games', 'Played cognitive wellness games')
    
    return render_template('games.html', 
                         name=session['full_name'],
                         email=session['email'],
                         games=BRAIN_GAMES)

@app.route('/community')
def community():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, author_name, content, created_at, likes_count 
            FROM community_posts 
            ORDER BY created_at DESC 
            LIMIT 50
        """)
        posts = cur.fetchall()
    except:
        posts = []
    finally:
        cur.close()
        conn.close()
    
    log_activity(session['user_id'], 'community', 'Community Visit', 'Visited support community')
    
    return render_template('community.html', 
                         name=session['full_name'],
                         email=session['email'],
                         posts=posts)

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login'})
    
    content = request.form.get('content')
    if content:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO community_posts (user_id, author_name, content) VALUES (%s, %s, %s)",
                (session['user_id'], session['full_name'], content)
            )
            conn.commit()
            
            log_activity(session['user_id'], 'community', 'Created Post', 'Shared in community')
            
            return redirect(url_for('community'))
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)})
        finally:
            cur.close()
            conn.close()
    
    return redirect(url_for('community'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    return render_template('profile.html', 
                         name=session['full_name'],
                         email=session['email'],
                         registered_at=session.get('registered_at', 'Unknown'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)