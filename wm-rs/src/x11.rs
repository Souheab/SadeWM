//! Pure protocol validation shared by property readers and regression tests.
use x11rb::protocol::xproto::GetPropertyReply;

pub fn property32(reply: &GetPropertyReply, kind: u32, min: usize, max: usize) -> Option<Vec<u32>> {
    let n = reply.value_len as usize;
    if reply.type_ != kind
        || reply.format != 32
        || reply.bytes_after != 0
        || n < min
        || n > max
        || n.checked_mul(4) != Some(reply.value.len())
    {
        return None;
    }
    Some(reply.value32()?.collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn malformed_properties_and_legacy_lengths() {
        let good = GetPropertyReply {
            type_: 6,
            format: 32,
            value_len: 2,
            value: vec![0; 8],
            ..Default::default()
        };
        assert_eq!(property32(&good, 6, 2, 2), Some(vec![0, 0]));
        let mut variants = vec![good.clone(); 7];
        variants[0].type_ = 31;
        variants[1].format = 8;
        variants[2].format = 16;
        variants[3].value.truncate(4);
        variants[4].value_len = 1;
        variants[5].bytes_after = 4;
        variants[6].value_len = u32::MAX;
        for bad in variants {
            assert!(property32(&bad, 6, 2, 2).is_none());
        }
        let legacy = GetPropertyReply {
            type_: 35,
            format: 32,
            value_len: 8,
            value: vec![0; 32],
            ..Default::default()
        };
        assert!(property32(&legacy, 35, 8, 9).is_some());
    }
}
