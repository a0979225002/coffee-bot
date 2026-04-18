from handlers.start import start, verify_key, set_name
from handlers.order import order_start, choose_drink, choose_temp, choose_bean
from handlers.auto import (
    auto_start, auto_confirm, auto_choose_drink,
    auto_choose_temp, auto_choose_bean, auto_choose_time, cancel_auto,
)
from handlers.skip import skip_cmd, skip_toggle
from handlers.info import help_cmd, apikey_cmd, status, who, list_all
