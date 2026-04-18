import sys
sys.path.append("property_bot")

def test_imports():
    import property_bot.main
    import property_bot.db
    import property_bot.tools
    import property_bot.graph
    import property_bot.whatsapp
    assert True
