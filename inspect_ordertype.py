from nado_protocol.utils.expiration import OrderType
try:
    print("OrderType members:")
    for member in OrderType:
        print(f"{member.name}: {member.value}")
except Exception as e:
    print(f"Error inspecting OrderType: {e}")
    print(f"Dir(OrderType): {dir(OrderType)}")
