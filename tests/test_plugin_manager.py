import pytest
import os
import json
import tempfile

from netfang.plugin_manager import PluginManager
from netfang.plugins.base_plugin import BasePlugin

class TestPlugin(BasePlugin):
    name = "TestPlugin"
    
    def __init__(self, config):
        super().__init__(config)
        self.connected_blacklisted_called = False
        self.blacklisted_mac = ""
        self.blacklisted_ssid = ""
    
    def on_setup(self):
        pass
    
    def on_enable(self):
        pass
    
    def on_disable(self):
        pass
    
    def on_connected_blacklisted(self, mac_address="", ssid="", *args, **kwargs):
        self.connected_blacklisted_called = True
        self.blacklisted_mac = mac_address
        self.blacklisted_ssid = ssid

class TestPluginManager:
    
    @pytest.fixture
    def plugin_manager(self):
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config = {
                "default_plugins": {
                    "testplugin": {"enabled": True}
                }
            }
            json.dump(config, f)
            config_path = f.name
        
        # Create plugin manager with the config
        pm = PluginManager(config_path)
        pm.load_config()
        
        # Add test plugin manually
        test_plugin = TestPlugin({"database_path": "test.db"})
        pm.plugins["TestPlugin"] = test_plugin
        
        yield pm
        
        # Cleanup
        os.unlink(config_path)
    
    def test_on_connected_blacklisted_passes_parameters(self, plugin_manager):
        """Test that on_connected_blacklisted correctly passes mac_address and ssid parameters."""
        # Set up test variables
        test_mac = "DE:AD:BE:EF:CA:FE"
        test_ssid = "TestBlacklistedNetwork"
        
        # Call the method
        plugin_manager.on_connected_blacklisted(test_mac, test_ssid)
        
        # Access our test plugin
        test_plugin = plugin_manager.plugins["TestPlugin"]
        
        # Assert it was called with the right parameters
        assert test_plugin.connected_blacklisted_called is True
        assert test_plugin.blacklisted_mac == test_mac
        assert test_plugin.blacklisted_ssid == test_ssid